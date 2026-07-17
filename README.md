# PixelForge

**Adaptive Multi-Variant Image Delivery & Optimization Platform**

A serverless-backed image pipeline that takes a single uploaded photo and
automatically produces every size/format variant a project needs — using
saliency-aware smart cropping so subjects don't get cut off when the
aspect ratio changes.

---


## Project Description

PixelForge lets you define a **Project** (e.g. "Blog Hero Images") with a
set of **variant profiles** — target dimensions, aspect ratio, and output
format. Every image you upload to that project is automatically resized,
smart-cropped, and format-optimized into all of those variants, with no
repeated manual configuration per image.

## Problem Statement

Content teams and solo creators routinely need the same source image in
several different sizes for different placements: a square thumbnail, a
wide desktop hero banner, a portrait mobile hero, a social share card.
Doing this manually in an image editor is slow, inconsistent, and easy to
get wrong — naive center-cropping frequently cuts off the actual subject
of the photo when the aspect ratio changes significantly.

## Why I Built This

This was built as an AWS capstone project to demonstrate a genuinely
serverless, event-driven architecture (S3 → Lambda) wrapped around a
real, non-trivial image-processing problem, rather than a toy "resize on
upload" tutorial. The saliency-aware cropping and per-project variant
profiles are the parts that make this a defensible engineering project
rather than a five-line Lambda function.

## Objectives

- Demonstrate an event-driven serverless architecture using S3 and Lambda
  as mandatory building blocks.
- Solve a real content-workflow problem (repetitive manual image exports)
  with a genuinely useful automation.
- Apply least-privilege IAM, scoped security groups, and cost-conscious
  design (Free Tier-eligible resources, automated storage cleanup).
- Build a complete, deployable full-stack application — not just a
  backend script.

## Features

- **Project-based variant profiles** — define target sizes/formats once
  per project; every upload is transformed into all of them.
- **Saliency-aware smart cropping** — an edge/gradient-energy heatmap
  estimates the visually important region of the source image and
  centers the crop on it, instead of naively cropping to center.
- **Format optimization** — converts to WebP (or JPEG/PNG) and reports
  bytes saved versus a naive same-format re-encode.
- **Direct-to-S3 browser uploads** via presigned URLs — the app server
  never proxies image bytes.
- **Live status polling** — the UI polls processing status and reveals
  variant download links as soon as the Lambda finishes.
- **Per-project analytics** — storage used, bytes saved, and processing
  success/failure counts.
- **Automated cost hygiene** — a scheduled Lambda purges orphaned/failed
  uploads after a configurable age.
- **Single-user auth** — simple, secure login for the project owner;
  registration is disabled after the first account is created.

## Architecture

```
Browser (Flask-rendered UI + vanilla JS)
   |
   | 1. Request a presigned upload URL
   v
Flask App (EC2, Ubuntu, Gunicorn + nginx)  <---->  Amazon RDS (PostgreSQL)
   |   - Auth, Projects, Variant Profiles          - users, projects,
   |   - Presigned URL generation                    variant_profiles,
   |   - Internal API for Lambda callbacks            images, image_variants,
   |                                                   analytics_events
   | 2. Browser PUTs the file directly to S3
   v
S3 "originals" bucket --(3. ObjectCreated event)--> Lambda: process-image
                                                          |
                                                          | 4. Fetch variant
                                                          |    manifest via
                                                          |    Flask internal
                                                          |    API
                                                          | 5. Saliency crop +
                                                          |    resize + WebP
                                                          v
                                          S3 "processed" bucket (variants)
                                                          |
                                                          | 6. POST results back
                                                          v
                                                    RDS updated -> dashboard

EventBridge (daily) --> Lambda: cleanup-orphans --> deletes stale uploads

CloudWatch  --> Logs for both Lambdas + app; IAM --> least-privilege roles
```

## AWS Services Used

| Service | Role |
|---|---|
| **Amazon S3** | Two buckets: `originals` (presigned browser uploads) and `processed` (generated variants) |
| **AWS Lambda** | `process-image` (S3-triggered smart crop/resize/convert pipeline) and `cleanup-orphans` (scheduled housekeeping) |
| **Amazon RDS (PostgreSQL)** | Stores users, projects, variant profiles, image/variant metadata, analytics events |
| **IAM** | Distinct least-privilege roles for each Lambda and the EC2 instance, scoped to specific S3 prefixes/buckets |
| **CloudWatch** | Logs for both Lambdas and the Flask app |
| **EventBridge** | Daily scheduled trigger for the cleanup Lambda |
| **Amazon EC2** | Hosts the Flask app (Ubuntu, t3.micro, Gunicorn behind nginx) |

Explicitly not used: API Gateway (Flask on EC2 already serves the HTTP
API directly), DynamoDB (RDS already models the relational data cleanly),
ECS/ECR/CodePipeline (out of scope for this project's size).

## Folder Structure

```
pixelforge/
├── app/                      # Flask application
│   ├── __init__.py           # App factory
│   ├── config.py             # Environment-driven configuration
│   ├── db.py                 # psycopg2 connection pool
│   ├── models.py             # Data access layer
│   ├── routes/                # Blueprints: auth, dashboard, projects, images, internal
│   ├── services/               # S3Service, auth_service
│   ├── templates/             # Jinja2 HTML templates
│   ├── static/                # CSS + vanilla JS (upload/poll/delete UI)
│   └── utils/                  # Validators, logging config
├── lambda/
│   ├── process_image/          # S3-triggered smart-crop/resize/convert function
│   └── cleanup_orphans/        # EventBridge-scheduled housekeeping function
├── db/
│   ├── schema.sql               # Full RDS schema
│   └── init_db.py               # Applies schema.sql to RDS
├── infra/                       # All deployment/provisioning scripts
├── tests/                       # pytest unit tests (validators)
├── requirements.txt
├── wsgi.py / run.py
├── .env.example
└── README.md / instructions.md
```

## Technology Stack

- **Backend**: Python, Flask, boto3, psycopg2
- **Frontend**: Server-rendered Jinja2 templates + vanilla JavaScript (no build step)
- **Database**: Amazon RDS (PostgreSQL)
- **Image processing**: Pillow + NumPy (inside the Lambda)
- **Infrastructure**: AWS CLI bash scripts (no CloudFormation/Terraform, by design, to keep every AWS API call visible and explainable in a capstone review)

## Installation

### Local development (without AWS)

```bash
git clone <your-repo-url> pixelforge
cd pixelforge
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in local/dev values
```

For fully local development you'll need a reachable PostgreSQL instance
(local or RDS) and two real S3 buckets — the presigned-upload flow and
Lambda pipeline both require actual S3, there is no local mock.

```bash
python db/init_db.py
python run.py
```

The app runs at `http://localhost:5000`.

## Configuration

All configuration is via environment variables — see `.env.example` for
the full list. Never commit a real `.env` file.

Key variables:

| Variable | Purpose |
|---|---|
| `FLASK_SECRET_KEY` | Flask session signing key |
| `S3_ORIGINALS_BUCKET` / `S3_PROCESSED_BUCKET` | Your two S3 bucket names |
| `DB_HOST` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | RDS connection details |
| `INTERNAL_API_KEY` | Shared secret the Lambdas use to call back into Flask |
| `MAX_UPLOAD_SIZE_BYTES` | Upload size cap (default 15 MB) |
| `ORPHAN_MAX_AGE_HOURS` | How old a stale upload must be before cleanup deletes it |

## Deployment

Full step-by-step deployment instructions — including all manual steps
that cannot be automated (RDS password, SSH key pair, IP allow-listing)
— are in **[instructions.md](./instructions.md)**.

Short version:

```bash
cd infra
bash setup_s3.sh
bash setup_iam.sh
bash setup_ec2.sh          # note the printed public IP
# --- manual: scp code to EC2, create .env, run deploy.sh on the instance ---
bash setup_rds.sh          # note the printed endpoint; add it to .env on EC2
bash package_lambda.sh
bash setup_lambda.sh
bash setup_eventbridge.sh
```

To tear everything down (and stop paying for it): `bash infra/teardown.sh`

## API Endpoints

### User-facing (session-authenticated)

| Method | Path | Description |
|---|---|---|
| GET/POST | `/register` | First-run account creation (single-user) |
| GET/POST | `/login` | Log in |
| POST | `/logout` | Log out |
| GET | `/home` | Dashboard: list projects |
| GET/POST | `/projects/new` | Create a project |
| GET | `/projects/<id>` | Project detail: profiles, upload UI, image gallery |
| POST | `/projects/<id>/delete` | Delete a project |
| POST | `/projects/<id>/profiles` | Add a variant profile |
| POST | `/projects/<id>/profiles/<id>/delete` | Remove a variant profile |
| GET | `/projects/<id>/analytics` | Per-project analytics |
| POST | `/projects/<id>/images/presign` | Get a presigned S3 upload URL |
| GET | `/projects/<id>/images/<id>/status` | Poll processing status |
| POST | `/projects/<id>/images/<id>/delete` | Delete an image and its variants |

### Internal (API-key authenticated, called only by the Lambdas)

| Method | Path | Description |
|---|---|---|
| GET | `/internal/images/lookup?key=` | Resolve an S3 key to an image_id |
| POST | `/internal/images/<id>/start` | Mark an image "processing" |
| GET | `/internal/images/<id>/profiles` | Fetch variant profile manifest |
| POST | `/internal/images/<id>/result` | Report success/failure + variant metadata |
| GET | `/internal/cleanup/stale-images` | List images eligible for cleanup |
| POST | `/internal/cleanup/images/<id>/purge` | Remove a purged image's DB row |

---

## Application Screenshots

| Feature | Preview |
|----------|---------|
| Login Page | <img width="1891" height="855" alt="image" src="https://github.com/user-attachments/assets/920db21d-4f6d-4de0-982b-1430575b247e" /> |
| Projects List | <img width="1917" height="857" alt="image" src="https://github.com/user-attachments/assets/1e2277f4-bd3e-4bbf-bcce-1c50f82b1e55" /> |
| Create Project | <img width="1901" height="843" alt="image" src="https://github.com/user-attachments/assets/975ad6aa-fdeb-4bd6-82f4-4d79a6390864" /> |
| Variant Profile Configuration | <img width="1900" height="853" alt="image" src="https://github.com/user-attachments/assets/ed4bcbda-4650-42db-a19d-b812eed32bae" /> |
| Generated Variants | <img width="1140" height="443" alt="image" src="https://github.com/user-attachments/assets/b71adc33-ce44-4a83-a5bf-8d5382f54647" /> |
| Analytics Dashboard | <img width="1907" height="852" alt="image" src="https://github.com/user-attachments/assets/f2c020e1-1531-4c5f-b803-553093987e2f" /> |

---

## Challenges Faced

- **Avoiding a Lambda-to-RDS direct connection.** Putting the Lambda
  inside the RDS VPC would add cold-start and connection-pooling
  complexity disproportionate to this project's scope. Routing Lambda
  writes through a small internal Flask API (secured with a shared
  secret) kept the architecture simpler without giving up correctness.
- **Smart cropping without a full ML dependency.** An edge/gradient
  energy centroid is a much lighter-weight signal than a face-detection
  model, but still meaningfully outperforms naive center-cropping on
  typical photos, and adds no extra Lambda layer or cold-start cost.
- **Keeping Pillow/NumPy Lambda-compatible.** Compiled wheels built on a
  different platform than the Lambda runtime will fail at import time;
  `infra/package_lambda.sh` explicitly fetches `manylinux2014_x86_64`
  wheels for the target Python version rather than trusting whatever the
  build machine produces.

## Future Improvements

- Add API Gateway + Lambda in front of the internal API if this ever
  needs to scale beyond a single EC2 instance.
- Replace the edge-energy saliency heuristic with a lightweight
  ONNX-based subject-detection model for better crop accuracy on complex
  scenes.
- Add multi-user support (the schema already has a `users` table ready
  for it).
- Add a CloudFront distribution in front of the processed bucket for
  actual CDN delivery, not just storage.

## What I Learned

Building this project deepened my understanding of event-driven
serverless architectures, least-privilege IAM design, and the practical
tradeoffs between "correct" architecture (e.g. Lambda-in-VPC) and
"appropriately scoped for the problem size" architecture. It also forced
a real decision about where image-processing intelligence should live —
in this case, favoring a fast, dependency-light heuristic over a heavier
ML approach given the Free Tier compute budget.

## Contact

**Heramb Chaudhari**

[![GitHub](https://img.shields.io/badge/GitHub-Heramb1221-black?style=for-the-badge&logo=github)](https://github.com/Heramb1221)

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Heramb%20Chaudhari-blue?style=for-the-badge&logo=linkedin)](https://www.linkedin.com/in/heramb-chaudhari)

[![Email](https://img.shields.io/badge/Email-hchaudhari1221%40gmail.com-red?style=for-the-badge&logo=gmail)](mailto:hchaudhari1221@gmail.com)
