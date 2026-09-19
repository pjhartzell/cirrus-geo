# Batch infrastructure

A [Batch task](tasks.md#lambda-or-batch) is not a single CloudFormation resource. Cirrus declares no Batch resources of its own, so every Batch task supplies them: at minimum a job definition, and in practice a compute environment, a job queue, and IAM roles as well.

This page covers those resources. The state machine definition around a Batch task is in [Batch tasks in a workflow](batch-workflow-structure.md).

## Declaring a Batch task

At minimum, a Batch task needs a job definition, a compute environment, a job
queue, and the IAM resources the compute environment references. The
following example declares all of them for a `Reproject` task:

```yaml
ReprojectBatchJob:
  Type: AWS::Batch::JobDefinition
  Properties:
    JobDefinitionName: !Sub '${ResourcePrefix}-Reproject'
    Type: Container
    Parameters:
      url: ""
      url_out: ""
    ContainerProperties:
      Command:
        - python
        - task.py
        - run
        - Ref::url
        - --output
        - Ref::url_out
      ResourceRequirements:
        - Type: VCPU
          Value: "4"
        - Type: MEMORY
          Value: "8000"
      Image: !Sub '123456789012.dkr.ecr.${AWS::Region}.amazonaws.com/some-image-name:latest'
      JobRoleArn: !GetAtt ReprojectJobRole.Arn

ReprojectComputeEnvironment:
  Type: AWS::Batch::ComputeEnvironment
  Properties:
    Type: MANAGED
    ComputeResources:
      Type: EC2
      AllocationStrategy: BEST_FIT_PROGRESSIVE
      MinvCpus: 0
      MaxvCpus: 256
      SecurityGroupIds: !Ref BatchSecurityGroupIds
      Subnets: !Ref BatchSubnets
      InstanceRole: !GetAtt ReprojectInstanceProfile.Arn
    State: ENABLED

ReprojectJobQueue:
  Type: AWS::Batch::JobQueue
  Properties:
    ComputeEnvironmentOrder:
      - Order: 1
        ComputeEnvironment: !Ref ReprojectComputeEnvironment
    State: ENABLED
    Priority: 1

ReprojectInstanceRole:
  Type: AWS::IAM::Role
  Properties:
    AssumeRolePolicyDocument:
      Version: '2012-10-17'
      Statement:
        - Effect: Allow
          Principal:
            Service:
              - ec2.amazonaws.com
          Action:
            - sts:AssumeRole
    ManagedPolicyArns:
      - arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role

ReprojectInstanceProfile:
  Type: AWS::IAM::InstanceProfile
  Properties:
    Roles:
      - Ref: ReprojectInstanceRole

ReprojectJobRole:
  Type: AWS::IAM::Role
  Properties:
    AssumeRolePolicyDocument:
      Version: '2012-10-17'
      Statement:
        - Effect: Allow
          Principal:
            Service:
              - ecs-tasks.amazonaws.com
          Action:
            - sts:AssumeRole
    Policies:
      - PolicyName: Cirrus
        PolicyDocument:
          Version: '2012-10-17'
          Statement:
            - Effect: Allow
              Action:
                - s3:GetObject
                - s3:PutObject
              Resource:
                - !Sub 'arn:aws:s3:::${CirrusPayloadBucket}/*'
```

The `ComputeEnvironment.ServiceRole` property is omitted: when left unset,
AWS Batch uses its own service-linked role, which is sufficient for a
standard compute environment.

### Job definition

The job definition is the only resource a Batch task strictly requires. It
specifies the container image to run, the command to run inside it, and the
container's resource requirements. See the [AWS job definition
CloudFormation
reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-batch-jobdefinition.html)
for the full property list.

**Job parameters.** The `Parameters` key declares named parameters, with optional defaults, that each submission fills in. A Cirrus Batch task receives its input payload's S3 URL as `url` and the URL it must write its output to as `url_out`, both produced by [`pre-batch`](../reference/lambda-functions.md#pre-batch). The `Command` references them with the `Ref::` syntax:

```yaml
Command:
  - python
  - task.py
  - run
  - Ref::url
  - --output
  - Ref::url_out
```

which Batch expands at submission time to `python task.py run <url> --output <url_out>`, the stac-task command line. A task with its own entry point must read from and write to those two URLs the same way. See [Batch tasks in a workflow](batch-workflow-structure.md) for how the workflow passes both.

**Resource requirements.** `ResourceRequirements` sets the VCPU, MEMORY, and
optionally GPU requirements for the job. These values are defaults that a submission can override through `ContainerOverrides`. The compute environment uses these
requirements, together with its `AllocationStrategy`, to pick an
instance type for the job.

**Image.** `Image` accepts a registry image reference
(`repository-url/image:tag`); omitting the registry defaults to Docker Hub.
Cirrus tasks typically pull from ECR. In a deployment with multiple
environments, parameterizing the image tag (`!Sub '...${ImageTag}'`, with
`ImageTag` set per environment) lets each environment pull a distinct image
version from the same repository.

### Compute environment

`Type: MANAGED` lets AWS Batch provision and scale instances; `Type: EC2`
compute resources give more control over instance selection than Fargate and
are typically favored for compute-intensive geospatial processing.

Compute environment scaling is governed by `MinvCpus`, `MaxvCpus`, and
`AllocationStrategy`. As jobs are submitted, the compute environment
allocates instances to match the total vCPU count requested by all
in-flight jobs, up to `MaxvCpus`, which is therefore also the practical
ceiling on how many jobs can run concurrently. Setting `MinvCpus` above zero
keeps that many vCPUs of instance capacity running at all times, which
avoids cold-start latency for the first jobs of a burst at the cost of
paying for idle capacity between bursts.

`ComputeResources.InstanceRole` takes an IAM instance profile ARN, not a
role ARN. See [IAM roles](#iam-roles).

!!! note "Naming compute environments"

    A compute environment is a replace-only resource: giving it an explicit
    `ComputeEnvironmentName` means an update that CloudFormation cannot
    perform in place (for example, changing `ComputeResources.Type`) fails
    on a name conflict between the existing environment and its
    replacement, rather than replacing it automatically. Omitting the name
    avoids that failure mode but produces autogenerated names. See
    [Updating Batch resources safely](#updating-batch-resources-safely) for
    the tradeoffs this creates during updates.

### Job queue

A job is submitted to a job queue, not directly to a compute environment.
The queue holds submitted jobs when the compute environment is saturated,
and `ComputeEnvironmentOrder` can list more than one compute environment
per queue, for example to prefer an On-Demand environment and overflow
into a Spot environment. See the [AWS job queue CloudFormation
reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-batch-jobqueue.html)
for supported configuration, including [scheduling
policies](https://docs.aws.amazon.com/batch/latest/userguide/scheduling-policies.html)
for prioritizing jobs within a shared queue.

### IAM roles

A compute environment references two IAM identities:

- `ServiceRole` is used by AWS Batch itself. Omit this property to use the
  AWS-managed service-linked role; a custom role is only needed for
  non-standard Batch permissions.
- `ComputeResources.InstanceRole` is the role for each EC2 container
  instance, supplied as an **instance profile** ARN rather than a role ARN.
  The instance role needs at minimum the
  `AmazonEC2ContainerServiceforEC2Role` managed policy so the ECS agent can
  register the instance and pull images; the example above pairs an
  `AWS::IAM::Role` with an `AWS::IAM::InstanceProfile` that references it.

A separate role, the job definition's `ContainerProperties.JobRoleArn`, is
assumed by the running container itself and should carry the permissions
the task's code needs (for example, S3 read/write on the payload bucket).
Keeping the instance role and the job role separate means the ECS agent's
permissions and the task code's permissions don't have to match, and a
compute environment shared by multiple job definitions doesn't grant every
task the union of all their permissions.

## Using the AWS Spot market

Spot instances reduce cost relative to On-Demand, at the cost of instances
being reclaimed by AWS with little notice. A compute environment opts into
Spot with `Type: SPOT`:

```yaml
ComputeResources:
  Type: SPOT
  AllocationStrategy: BEST_FIT_PROGRESSIVE
  SpotIamFleetRole: !GetAtt EC2SpotRole.Arn
  InstanceRole: !GetAtt BatchInstanceProfile.Arn
  InstanceTypes:
    - r5.xlarge
    - r5.2xlarge
    - r5.4xlarge
  MinvCpus: 0
  MaxvCpus: 5000
```

`SpotIamFleetRole` is required only when `AllocationStrategy` is `BEST_FIT` or unset; the progressive and capacity-optimized strategies do not use it. `BEST_FIT_PROGRESSIVE` requests progressively across the listed
instance types that best match the job's resource requirements, accepting
any of them, which tends to fill Spot capacity faster than `BEST_FIT`
(which waits for its single best-fit type). Restricting `InstanceTypes` to a
set with a consistent vCPU-to-memory ratio matching the job's
`ResourceRequirements` avoids wasting the unused capacity of an
oversized instance.

Because Spot reclamation surfaces as a killed job, error handling in the
workflow matters more with Spot than with On-Demand. See [Batch retries
vs. Step Functions retries](batch-workflow-structure.md#batch-retries-vs-step-functions-retries).

## Launch templates

A launch template customizes the EC2 instances a compute environment
starts, most commonly to increase the root EBS volume size beyond its default,
since a Batch job's `ResourceRequirements` cannot request disk space
directly:

```yaml
ReprojectLaunchTemplate:
  Type: AWS::EC2::LaunchTemplate
  Properties:
    LaunchTemplateData:
      BlockDeviceMappings:
        - DeviceName: /dev/xvda
          Ebs:
            VolumeSize: 500
            VolumeType: gp3
            DeleteOnTermination: true
            Encrypted: true
```

referenced from the compute environment as:

```yaml
LaunchTemplate:
  LaunchTemplateId: !Ref ReprojectLaunchTemplate
  Version: $Latest
```

Updating a launch template does not affect any compute environment already
running against it: the launch template version is resolved once, at
compute environment creation, and cached. Making a launch template change
take effect on an existing compute environment requires recreating the
compute environment so it re-resolves `$Latest` (or whichever version is
referenced). See [Updating Batch resources
safely](#updating-batch-resources-safely).

## Other considerations

**Shared resources.** Prefer a dedicated job definition, compute
environment, and job queue per Batch task over sharing them across tasks.
Sharing reduces duplication but couples the tasks' resource requirements,
instance selection, and IAM permissions together, and increases the blast
radius of any single resource change.

**Batch quotas.** AWS limits an account to 50 compute environments and 50
job queues per Region. A deployment with many Batch tasks, especially one
using the [blue/green update
strategy](#downtime-unacceptable-bluegreen-updates) below, which
doubles the resource count per task while a change is rolling out, needs
enough quota headroom for that doubling, or needs to consolidate compute
environments and job queues across tasks.

**Subnets.** Compute resources in a private subnet incur NAT Gateway data
processing charges for traffic leaving the VPC (for example, pulling images
from ECR or reading/writing S3 in another Region). Where the security
posture allows it, a public subnet avoids that cost. Restrict inbound
access with security groups regardless. In particular, do not open SSH
(port 22) to compute instances.

## Updating Batch resources safely

*The rest of this page covers failure modes that only matter when you
**update** existing Batch infrastructure: job definition revisions,
compute environment replacement, job queue deletion. Skip this section
until you need to change a Batch resource that is already deployed and
processing jobs.*

Several CloudFormation update behaviors around Batch resources can disrupt
in-flight or newly-started workflow executions. None of them are Cirrus-specific; they follow from how CloudFormation and AWS Batch handle updates
to these resource types.

### Failure modes

**Executions started mid-deployment can reference a stale job definition.**
A Step Functions state machine calling `SubmitJob` (through a `!Sub` reference to the job definition resource) resolves to a specific job
definition revision ARN. When CloudFormation deploys a new job definition
revision, it deactivates the old revision *before* updating the state
machine. An execution that starts a Batch task in the window between the
old revision's deactivation and the state machine update fails with a
reference to a deactivated revision.

**A rolled-back deployment does not restore the previous job definition
revision; it creates a new one.** If CloudFormation errors out during
deployment and rolls back a job definition update, AWS Batch does not
reactivate the original revision. Instead, CloudFormation redeploys the
pre-update definition as a *new* revision:

```text
Job definition       A       B      A
Revision number      1   ->  2  ->  3
```

Revision 2 (B) deactivates revision 1 on creation; on rollback, revision 3
(A again) deactivates revision 2. The state machine, however, was never
updated past its original reference to revision 1, so after this sequence
it points at a deactivated revision permanently, not just for the
deployment window. Fixing it requires another deployment or a manual state
machine update.

**Deleting a job queue kills every job on it.** Removing or renaming a job
queue resource in a template deletes the queue, which terminates any jobs
still running or queued on it. This applies to any change that causes
CloudFormation to replace the job queue resource, not only an intentional
deletion.

### Choosing an update strategy

Which of these failure modes matter, and how much, depends on uptime
requirements and how continuously the pipeline runs jobs.

#### Downtime unacceptable: blue/green updates

If jobs run continuously and any window of failed executions is
unacceptable, avoid updating Batch resources in place. Instead, maintain
two parallel copies of every Batch resource for a task, conventionally
suffixed `RevA` and `RevB`, and alternate which copy is live:

```text
ReprojectBatchJobRevA              ReprojectBatchJobRevB
ReprojectLaunchTemplateRevA        ReprojectLaunchTemplateRevB
ReprojectComputeEnvironmentRevA    ReprojectComputeEnvironmentRevB
ReprojectJobQueueRevA              ReprojectJobQueueRevB
ReprojectInstanceRoleRevA          ReprojectInstanceRoleRevB
ReprojectInstanceProfileRevA       ReprojectInstanceProfileRevB
```

Name the compute environment and job queue explicitly in each revision, so
an update always targets the inactive copy rather than replacing the live
one in place.

To update, say, the launch template while revision A is live:

1. Copy `ReprojectLaunchTemplateRevA` to `ReprojectLaunchTemplateRevB` with
   the change applied.
2. Copy `ReprojectComputeEnvironmentRevA` to
   `ReprojectComputeEnvironmentRevB`, pointing it at
   `ReprojectLaunchTemplateRevB`.
3. Copy `ReprojectJobQueueRevA` to `ReprojectJobQueueRevB`, pointing it at
   `ReprojectComputeEnvironmentRevB`.
4. Update the workflow's job queue reference from
   `ReprojectJobQueueRevA` to `ReprojectJobQueueRevB`.

CloudFormation creates the new (B) resources and updates the state machine
reference in that order. If deployment fails at any point, the state
machine and the A resources are untouched, and executions already running
or newly started continue to use them.

Once the deployment succeeds and running A jobs have drained, remove the A
resources. The next update alternates back to A. In practice, copying every
resource on each update, rather than only the one that changed, keeps
each revision fully self-consistent.

This strategy doubles the Batch resource count per task while a revision
change is in flight; account for that against the [50-per-Region compute
environment and job queue quota](#other-considerations).

#### Downtime acceptable, jobs intermittent

If jobs run intermittently, and a failed execution during a deployment
window can simply be retried, update Batch resources in place rather than
maintaining two revisions. In this case, omitting `ComputeEnvironmentName`
and job queue names avoids the replace-on-name-conflict failure mode
described in [Compute environment](#compute-environment), at the cost of
autogenerated names.
