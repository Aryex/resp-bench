# EC2 Instance Setup for Stability Testing

## Launch Instance

```bash
aws ec2 run-instances \
  --region us-east-1 \
  --image-id ami-0f981d108db0b44c6 \
  --instance-type c5.xlarge \
  --key-name lehminh \
  --metadata-options "HttpEndpoint=enabled,HttpTokens=required,HttpPutResponseHopLimit=2" \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=lehminh-resp-bench-stability}]' \
  --query 'Instances[0].InstanceId' \
  --output text
```

## Get Public IP

```bash
aws ec2 describe-instances \
  --region us-east-1 \
  --filters "Name=tag:Name,Values=resp-bench-stability" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text
```

## SSH

```bash
ssh -i ~/.ssh/lehminh.pem ubuntu@ec2-3-239-118-213.compute-1.amazonaws.com
```

## Terminate

```bash
aws ec2 terminate-instances --region us-east-1 --instance-ids <instance-id>
```
