# PixelForge — Detailed Deployment Instructions

This guide assumes you are deploying PixelForge for the very first time
and have never touched this AWS account for this project before. Follow
the sections in order.

---

## 1. Prerequisites

- An AWS account with billing enabled (some steps use Free Tier eligible
  resources, but you are responsible for confirming Free Tier eligibility
  for your account).
- AWS CLI v2 installed and configured (`aws configure`) with an IAM user
  or role that has permission to create S3 buckets, Lambda functions,
  IAM roles, EC2 instances, RDS instances, and EventBridge rules.
- Python 3.12 and `pip` installed locally (for packaging Lambdas).
- `zip` installed locally (for packaging Lambdas).
- An SSH client.
- This repository downloaded/cloned locally.

Confirm your CLI identity before doing anything else:

```bash
aws sts get-caller-identity
```

If this fails, fix your AWS CLI configuration before continuing.

---

## 2. AWS Region

Every script in `infra/` is pinned to **ap-south-1** via `infra/config.sh`.
Do not deploy resources across multiple regions unless you update every
script consistently — cross-region S3 event notifications to Lambda are
not supported.

---

## 3. Configure `infra/config.sh`

Open `infra/config.sh` and edit every value marked `CHANGE-ME`:

| Variable | How to choose it |
|---|---|
| `S3_ORIGINALS_BUCKET` | Must be **globally unique** across all of AWS. Try `pixelforge-originals-<yourname>-<random4digits>`. |
| `S3_PROCESSED_BUCKET` | Same rule, different suffix, e.g. `pixelforge-processed-<yourname>-<random4digits>`. |
| `EC2_KEY_PAIR_NAME` | See step 4 below. |
| `EC2_SSH_CIDR` | Your current public IP in CIDR form, e.g. `203.0.113.4/32`. Find yours at https://checkip.amazonaws.com. |
| `INTERNAL_API_BASE_URL` | Leave as the placeholder for now — you'll fill this in after step 6 (EC2 launch). |
| `INTERNAL_API_KEY` | Generate a long random string, e.g. `openssl rand -hex 32`. |

---

## 4. Create an EC2 key pair (manual — required)

```bash
aws ec2 create-key-pair \
  --key-name pixelforge-key \
  --region ap-south-1 \
  --query 'KeyMaterial' --output text > pixelforge-key.pem
chmod 400 pixelforge-key.pem
```

Set `EC2_KEY_PAIR_NAME="pixelforge-key"` in `infra/config.sh`. **Keep
`pixelforge-key.pem` safe — it is never stored in AWS and cannot be
downloaded again.**

---

## 5. S3 setup

```bash
cd infra
bash setup_s3.sh
```

This creates both buckets, enables default encryption, blocks all public
access, applies CORS to the originals bucket (so the browser can PUT
directly to it), and sets a lifecycle rule to abort incomplete multipart
uploads after a day.

---

## 6. IAM setup

```bash
bash setup_iam.sh
```

Creates three least-privilege roles (process-image Lambda, cleanup
Lambda, EC2 instance) and the EC2 instance profile. Safe to re-run.

---

## 7. EC2 setup

```bash
bash setup_ec2.sh
```

This launches a `t3.micro` Ubuntu 24.04 instance, creates a security
group allowing SSH only from `EC2_SSH_CIDR` and HTTP (port 80) from
anywhere, and attaches the IAM instance profile from step 6.

**Copy the printed Public IP.** Update `infra/config.sh`:

```bash
export INTERNAL_API_BASE_URL="http://<the-public-ip-you-just-got>"
```

---

## 8. Deploy the application code to EC2 (manual)

From your local machine, in the project root:

```bash
scp -i pixelforge-key.pem -r . ubuntu@<public-ip>:/opt/pixelforge
ssh -i pixelforge-key.pem ubuntu@<public-ip>
```

Once connected to the instance:

```bash
cd /opt/pixelforge
cp .env.example .env
nano .env   # fill in FLASK_SECRET_KEY, S3 bucket names, INTERNAL_API_KEY
            # (DB_* values come after step 9 — RDS doesn't exist yet)
```

Do not run `deploy.sh` yet — you need real RDS values first (next step).

---

## 9. RDS setup

Back on your **local machine** (not the EC2 instance):

```bash
cd infra
bash setup_rds.sh
```

You will be prompted to type and confirm a master database password —
this is never written to a file or logged. The script takes 5-10 minutes
and prints the RDS endpoint when done.

**On the EC2 instance**, edit `/opt/pixelforge/.env` and fill in:

```
DB_HOST=<the endpoint setup_rds.sh printed>
DB_PORT=5432
DB_NAME=pixelforge
DB_USER=pixelforge_app
DB_PASSWORD=<the password you entered interactively>
```

---

## 10. Run the app deployment script (on EC2)

Still on the EC2 instance:

```bash
cd /opt/pixelforge
sudo bash infra/deploy.sh
```

This installs system packages, creates a Python virtualenv, installs
dependencies, applies the database schema (`db/init_db.py`), sets up a
systemd service (`pixelforge.service`) running Gunicorn, and configures
nginx as a reverse proxy on port 80.

Verify it's running:

```bash
systemctl status pixelforge
curl -I http://localhost
```

Visit `http://<public-ip>/` in your browser — you should see the
registration page (single-user setup).

---

## 11. Lambda packaging and deployment

Back on your **local machine**:

```bash
cd infra
bash package_lambda.sh
bash setup_lambda.sh
```

`package_lambda.sh` builds `lambda/process_image/package.zip` and
`lambda/cleanup_orphans/package.zip`, fetching Lambda-compatible
(`manylinux2014_x86_64`) wheels for Pillow/NumPy.

`setup_lambda.sh` creates both functions, wires S3 → process-image
event notifications, and sets each function's environment variables
(including `INTERNAL_API_BASE_URL` and `INTERNAL_API_KEY` from
`infra/config.sh` — make sure those are correct before running this).

---

## 12. EventBridge schedule for cleanup

```bash
bash setup_eventbridge.sh
```

Schedules `cleanup-orphans` to run daily at 03:00 UTC. To test it
immediately instead of waiting:

```bash
aws lambda invoke --function-name pixelforge-cleanup-orphans /tmp/result.json
cat /tmp/result.json
```

---

## 13. Security Groups (reference)

| Security group | Inbound rules |
|---|---|
| `pixelforge-app-sg` (EC2) | 22/tcp from `EC2_SSH_CIDR` only; 80/tcp from `0.0.0.0/0` |
| `pixelforge-rds-sg` (RDS) | 5432/tcp from `pixelforge-app-sg` only |

RDS is created with `--no-publicly-accessible`, so it is unreachable
from outside the VPC even if the security group were misconfigured.

---

## 14. Load Balancer

Not used in this deployment — a single `t3.micro` instance behind nginx
is sufficient for a capstone demo and keeps costs at zero beyond the
Free Tier. If you need to scale, put an Application Load Balancer in
front of an Auto Scaling Group of the same instance type; the app is
already stateless (sessions are Flask signed-cookie sessions, not
server-side), so this requires no code changes.

---

## 15. Running locally (without full AWS)

Not fully supported — the presigned-upload flow and Lambda pipeline both
require real S3 buckets and a reachable Lambda function, so "local"
development in practice means running Flask locally while still pointing
at real AWS S3/RDS resources:

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # point DB_HOST/S3 buckets at your real AWS resources
python db/init_db.py
python run.py
```

---

## 16. Testing

Unit tests (validators only — no AWS/DB required):

```bash
pip install pytest
pytest tests/ -v
```

End-to-end testing after deployment:

1. Visit `http://<ec2-public-ip>/` and register the single account.
2. Create a project, add a variant profile (e.g. `thumbnail`, 200×200, WebP).
3. Upload a JPEG or PNG image.
4. Watch the status pill go `pending` → `processing` → `done` (polls
   every 2.5s). If it stays on `pending`, check the Lambda's CloudWatch
   logs (see Troubleshooting).
5. Click a variant chip to download/view the processed image.
6. Check `/projects/<id>/analytics` for bytes-saved reporting.

---

## 17. Troubleshooting

**Upload button does nothing / presign request fails**
Check the browser console. If you see a CORS error, re-run
`bash infra/setup_s3.sh` (it re-applies the CORS configuration) and
confirm `S3_ORIGINALS_BUCKET` in `.env` on EC2 matches the actual bucket.

**Status stays "pending" forever**
The S3 → Lambda trigger likely isn't wired correctly, or the Lambda is
erroring before it can call the internal "mark processing" endpoint.
Check logs:
```bash
aws logs tail /aws/lambda/pixelforge-process-image --follow
```

**Status becomes "failed" immediately**
Check the same log stream — the error message is also stored on the
image record and shown in the UI under the failed image. Common causes:
Pillow/NumPy wheels weren't built for the right platform (re-run
`package_lambda.sh` and `setup_lambda.sh`), or the internal API key in
the Lambda's environment doesn't match the one in the app's `.env`.

**Lambda can't reach the Flask internal API**
Confirm the EC2 security group allows inbound 80/tcp from `0.0.0.0/0`
(Lambda has no VPC networking here, so it calls over the public
internet) and that nginx/Gunicorn are actually running
(`systemctl status pixelforge nginx`).

**"unauthorized" from `/internal/...` endpoints**
`INTERNAL_API_KEY` in the EC2 `.env` file must exactly match the value
set on both Lambda functions. If you change it, update all three places
and re-run `bash infra/setup_lambda.sh` to push the new value to the
Lambdas, then `sudo systemctl restart pixelforge` on EC2.

**RDS connection refused from EC2**
Confirm `pixelforge-rds-sg` allows 5432/tcp from `pixelforge-app-sg`
(not from a CIDR) — `setup_rds.sh` sets this up automatically, but if
you created the EC2 instance after RDS, security group references can
be stale. Re-run `setup_rds.sh`; it's safe to re-run for the security
group step, though it will error on `create-db-instance` if the DB
already exists (that's expected, ignore it).

**502 Bad Gateway from nginx**
Gunicorn isn't running. Check `journalctl -u pixelforge -f` for a
Python traceback — usually a missing/incorrect `.env` value causing
`Config.validate()` to raise on startup.

---

## 18. Cleanup

To delete every AWS resource this project created and stop being billed
for them:

```bash
cd infra
bash teardown.sh
```

This deletes: the EventBridge rule, both Lambda functions, both S3
buckets (and their contents), the RDS instance, the EC2 instance, the
security groups, and all three IAM roles/instance profile.

**This is destructive and irreversible** (no RDS final snapshot is
taken). Only run it when you're actually done with the project.
