"""Tag-based AWS teardown — so no paid infra is ever left running by accident.

Every AWS resource DevOps creates is tagged Project=ai-org (+ project_id,
ephemeral, created_by). This script finds them BY TAG and reclaims them. It is
the answer to "what's the cleanup plan for anything spun up during testing":
one command, and it LISTS what it will destroy before doing anything.

Usage (from the backend container or any host with the AWS creds):

    python -m app.devops.teardown_aws                 # dry run: list only
    python -m app.devops.teardown_aws --yes           # stop instances, delete ECR + records
    python -m app.devops.teardown_aws --yes --terminate   # also TERMINATE ephemeral instances

Defaults are conservative: without --yes nothing is deleted; without --terminate
instances are STOPPED (not terminated), matching the cost-control plan of keeping
one reusable instance and stopping it between tests.
"""
import sys

from app.config import settings

_TAG_PROJECT = "ai-org"


def _boto():
    import boto3
    return boto3.session.Session(region_name=settings.aws_region)


def _instances(sess):
    ec2 = sess.client("ec2")
    resp = ec2.describe_instances(Filters=[
        {"Name": "tag:Project", "Values": [_TAG_PROJECT]},
        {"Name": "instance-state-name",
         "Values": ["pending", "running", "stopping", "stopped"]},
    ])
    out = []
    for res in resp.get("Reservations", []):
        for inst in res.get("Instances", []):
            tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
            out.append({
                "id": inst["InstanceId"],
                "state": inst["State"]["Name"],
                "type": inst.get("InstanceType"),
                "ephemeral": tags.get("ephemeral") == "true",
                "ip": inst.get("PublicIpAddress"),
            })
    return out


def _ecr_repos(sess):
    ecr = sess.client("ecr")
    repos = []
    paginator = ecr.get_paginator("describe_repositories")
    for page in paginator.paginate():
        for r in page.get("repositories", []):
            if r["repositoryName"].startswith("ai-org/"):
                repos.append(r["repositoryName"])
    return repos


def _dns_records(sess):
    if not settings.route53_zone_id:
        return []
    r53 = sess.client("route53")
    recs = []
    paginator = r53.get_paginator("list_resource_record_sets")
    for page in paginator.paginate(HostedZoneId=settings.route53_zone_id):
        for rr in page.get("ResourceRecordSets", []):
            if rr["Type"] == "A" and rr["Name"].rstrip(".").endswith(
                    settings.apps_subdomain):
                recs.append(rr)
    return recs


def main(argv) -> int:
    do = "--yes" in argv
    terminate = "--terminate" in argv
    sess = _boto()

    instances = _instances(sess)
    repos = _ecr_repos(sess)
    records = _dns_records(sess)

    print(f"AWS teardown — region {settings.aws_region}, tag Project={_TAG_PROJECT}")
    print(f"\nEC2 instances ({len(instances)}):")
    for i in instances:
        print(f"  {i['id']}  {i['type']}  {i['state']}  "
              f"ephemeral={i['ephemeral']}  ip={i['ip']}")
    print(f"\nECR repositories ({len(repos)}):")
    for r in repos:
        print(f"  {r}")
    print(f"\nRoute53 A records under {settings.apps_subdomain} ({len(records)}):")
    for rr in records:
        print(f"  {rr['Name']}")

    if not do:
        print("\n(dry run — nothing deleted. Re-run with --yes to act, "
              "--terminate to terminate ephemeral instances.)")
        return 0

    ec2 = sess.client("ec2")
    for i in instances:
        if terminate and i["ephemeral"]:
            print(f"terminating {i['id']} (ephemeral)")
            ec2.terminate_instances(InstanceIds=[i["id"]])
        elif i["state"] == "running":
            print(f"stopping {i['id']}")
            ec2.stop_instances(InstanceIds=[i["id"]])

    ecr = sess.client("ecr")
    for r in repos:
        print(f"deleting ECR repo {r}")
        ecr.delete_repository(repositoryName=r, force=True)

    if records and settings.route53_zone_id:
        r53 = sess.client("route53")
        changes = [{"Action": "DELETE", "ResourceRecordSet": rr} for rr in records]
        print(f"deleting {len(changes)} Route53 record(s)")
        r53.change_resource_record_sets(
            HostedZoneId=settings.route53_zone_id,
            ChangeBatch={"Changes": changes},
        )

    print("\nDone. (SSM SecureString params under /ai-org/* are removed by the "
          "driver's teardown; sweep them with `aws ssm delete-parameters` if any "
          "remain.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
