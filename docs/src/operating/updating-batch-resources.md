# Updating Batch resources

Changing a Batch task's resources in a deployment that is processing jobs has failure modes that a first deploy does not. This page covers them and two update strategies. Declaring the resources themselves is on [Batch infrastructure](../building-pipelines/batch-infrastructure.md); the core stack's own update procedure is on [Deploying to AWS](deploying.md#updating).

Several CloudFormation update behaviors around Batch resources can disrupt
in-flight or newly-started workflow executions. None of them are Cirrus-specific; they follow from how CloudFormation and AWS Batch handle updates
to these resource types.

## Failure modes

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

## Choosing an update strategy

Which of these failure modes matter, and how much, depends on uptime
requirements and how continuously the pipeline runs jobs.

### Downtime unacceptable: blue/green updates

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
environment and job queue quota](../building-pipelines/batch-infrastructure.md#other-considerations).

### Downtime acceptable, jobs intermittent

If jobs run intermittently, and a failed execution during a deployment
window can simply be retried, update Batch resources in place rather than
maintaining two revisions. In this case, omitting `ComputeEnvironmentName`
and job queue names avoids the replace-on-name-conflict failure mode
described in [Compute environment](../building-pipelines/batch-infrastructure.md#compute-environment), at the cost of
autogenerated names.
