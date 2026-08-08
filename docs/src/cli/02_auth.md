# Authentication

Because the Cirrus CLI interacts directly with AWS resources via the AWS python API
with the boto3 library, you will have to be authenticated with AWS. We
recommend following your organization's best practice recommendations for
authentication. One way you could do so is to use the [AWS CLI tool](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).

Look [here](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html) for an in depth explanation of authentication options with the AWS
command line tool and how to configure SSO login.

The Cirrus CLI will only need to be installed once, but authenticating with AWS
will be necessary for each new session as AWS credentials expire and must be
refreshed every so often. This can be easily accomplished with the AWS CLI
single sign on (SSO) option.

After you have built your config file according to organizational or personal
preference you can login with

``` bash
aws sso login --profile your-named-profile
```

Once you have successfully SSO'd setup will be complete for the Cirrus CLI
