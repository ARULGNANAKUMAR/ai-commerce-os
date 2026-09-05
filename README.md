# AI Commerce OS — Phase 5

> **Razorpay AI Buildathon 2026 · Track 01 — AI Growth & Agentic Commerce**

**AI Commerce OS** is an AI-powered commerce platform that turns a natural-language customer conversation into a controlled shopping journey: product discovery → recommendation → upsell/cross-sell → cart → permission gate → checkout → payment → audit trail → revenue analytics.

The core product idea is:

> **Turn a customer conversation into a bounded, explainable, and auditable transaction.**


---

## 🚀 What AI Commerce OS Does

AI Commerce OS is designed for merchants who want an AI agent to participate in the sales journey without giving the agent unlimited control over business or financial actions.

### Customer side

- Conversational product discovery
- Product search and filtering
- Product comparison
- AI recommendations
- Upselling
- Cross-selling
- Cart creation and modification
- Checkout initiation
- Multi-language commerce support including English, Tamil and Tanglish
- Payment success/failure and retry flows

### Merchant side

- Product catalog management
- AI provider configuration
- Permission and spending limits
- Human approval controls
- Workflow builder
- Workflow execution
- AI architecture analysis
- Audit timeline
- Payment/order management
- Revenue analytics
- Admin and usage monitoring

### Safety and control

The AI agent does **not** receive unlimited financial authority.

Financial capabilities are deny-by-default and can be bounded by:

- capability permissions
- maximum payment amount
- maximum refund amount
- approval requirements
- customer confirmation
- audit logging

---

# 🧠 Core Concept

Traditional e-commerce:

```text
Search → Product Page → Compare → Cart → Checkout → Payment
```

AI Commerce OS:

```text
Customer Conversation
        ↓
AI understands intent
        ↓
Search / Compare
        ↓
Recommendation
        ↓
Upsell / Cross-sell
        ↓
Customer decision
        ↓
Cart
        ↓
Permission + Limit Check
        ↓
Customer Confirmation
        ↓
Checkout
        ↓
Payment
        ↓
Audit + Analytics
```

The AI becomes a **commerce agent**, not just a chatbot.

---

# 🧊 3D-Style Working Flow

The following Mermaid diagram represents the platform as a layered 3D-style flow. GitHub renders Mermaid diagrams directly in supported Markdown views.

```mermaid
flowchart TB

    subgraph L1["① CUSTOMER EXPERIENCE"]
        A["👤 Customer"]
        B["💬 Conversational AI"]
        C["🔎 Product Discovery"]
        D["📊 Compare Products"]
    end

    subgraph L2["② AI SALES ENGINE"]
        E["🤖 Recommendation"]
        F["⬆️ Upsell"]
        G["➕ Cross-sell"]
        H["🛒 Cart"]
    end

    subgraph L3["③ CONTROL LAYER"]
        I["🛡 Permission Check"]
        J["💰 Amount Limits"]
        K["👤 Human Approval"]
        L["✅ Customer Confirmation"]
    end

    subgraph L4["④ TRANSACTION LAYER"]
        M["💳 Checkout"]
        N["Razorpay Test / Demo Payment"]
        O["🔐 Signature Verification"]
        P["🔁 Failure + Retry"]
    end

    subgraph L5["⑤ BUSINESS INTELLIGENCE"]
        Q["🧾 Audit Trail"]
        R["📈 Revenue Analytics"]
        S["📊 Conversion / AOV"]
        T["🧠 AI Growth Insights"]
    end

    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
    E --> G
    F --> H
    G --> H

    H --> I
    I --> J
    J --> K
    K --> L

    L --> M
    M --> N
    N --> O
    O -->|Success| Q
    O -->|Failure| P
    P --> M

    Q --> R
    R --> S
    R --> T
```

---

# 🏗️ 3D-Style System Architecture

The architecture is separated into five conceptual layers.

```text
                         ┌─────────────────────────────┐
                        /      CUSTOMER LAYER          /|
                       /  Chat • Search • Cart       / |
                      /_____________________________/  |
                      |                             |  |
                      |       AI COMMERCE           |  |
                      |  Recommendation • Upsell   |  |
                      |  Cross-sell • Copilot      |  |
                      |_____________________________| /
                      |                             |/
                      |     CONTROL & SAFETY       |
                      | Permission • Limits        |
                      | Approval • Confirmation    |
                      |_____________________________|
                      |                             |
                      |     TRANSACTION LAYER       |
                      | Checkout • Orders • Payment|
                      | Razorpay • Retry • Refund  |
                      |_____________________________|
                      |                             |
                      |     DATA & INTELLIGENCE     |
                      | MongoDB • Audit • Analytics |
                      | AI Memory • Usage          |
                      |_____________________________|
                      |                             |
                      |     PLATFORM FOUNDATION     |
                      | Flask • Auth • Security     |
                      | REST APIs • Configuration  |
                      |_____________________________|
```

### Architecture relationship

```mermaid
flowchart LR

    U["👤 Customer"] --> UI["Web UI / Chat"]

    UI --> API["Flask API Layer"]

    API --> AUTH["Authentication & Security"]
    API --> COM["AI Commerce Engine"]
    API --> WF["Workflow Engine"]
    API --> PAY["Payment Engine"]
    API --> ANA["Analytics"]

    COM --> CAT["Product Catalog"]
    COM --> AI["AI Provider Layer"]
    COM --> PERM["Permission Engine"]
    COM --> CART["Cart Service"]

    WF --> ARCH["AI Architecture Engine"]
    WF --> MEM["AI Memory"]

    PAY --> RZP["Razorpay Test API"]
    PAY --> ORD["Orders"]
    PAY --> WEB["Webhooks"]

    AUTH --> DB["MongoDB"]
    CAT --> DB
    AI --> DB
    PERM --> DB
    CART --> DB
    WF --> DB
    PAY --> DB
    ANA --> DB

    DB --> AUD["Audit Logs"]
```

---

# 🔄 End-to-End Agentic Commerce Flow

## Step 1 — Customer Intent

The customer communicates naturally.

Example:

```text
"I need a laptop for programming under ₹60,000."
```

The AI commerce layer understands the request and searches the merchant's catalog.

---

## Step 2 — Product Discovery

The search service can use:

- keyword matching
- category
- brand
- price range
- stock status
- product relevance

The result is returned from the merchant's own catalog.

---

## Step 3 — Recommendation

The recommendation engine identifies products that match the customer's requirements.

The platform records recommendation events so the merchant can later understand recommendation-driven activity.

---

## Step 4 — Upsell and Cross-sell

The agent can suggest:

### Upsell

A higher-tier or premium alternative.

```text
"You could also consider the higher-performance model."
```

### Cross-sell

A complementary product.

```text
"Would you like to add a wireless mouse or laptop bag?"
```

These actions are controlled by commerce permissions.

---

## Step 5 — Cart

The selected products are added to the customer's cart.

The server calculates the cart total.

The client should not be trusted to determine the final payable amount.

---

## Step 6 — Permission Gate

Before financial actions, the permission engine checks the requested capability.

Important capabilities include:

```text
product_read
product_search
product_compare
recommendation
upsell
cross_sell
cart_create
checkout_create
payment_request
refund_request
```

Financial capabilities are designed to be disabled by default and can have amount limits and approval requirements.

---

## Step 7 — Customer Confirmation

Before proceeding to a payment action, the customer is given a clear confirmation step.

This creates a human-readable boundary between:

```text
AI recommendation
```

and

```text
financial action
```

---

## Step 8 — Checkout and Payment

The payment service:

1. resolves the cart amount
2. checks the payment permission
3. checks the configured limit
4. creates a payment order
5. stores the order in MongoDB
6. creates a payment record
7. writes an audit event
8. returns checkout information

### Razorpay integration

The project contains a Razorpay REST client.

When Test Mode credentials are configured, real Razorpay API requests can be attempted.

When the Razorpay secret is not configured, the project can run its deterministic demo/mock payment flow for development and demonstration.

**Do not describe the mock flow as a real Razorpay transaction.**

---

# 💳 Payment Security Flow

```mermaid
sequenceDiagram
    participant C as Customer
    participant UI as Web UI
    participant API as Flask API
    participant P as Payment Service
    participant R as Razorpay
    participant DB as MongoDB

    C->>UI: Confirm checkout
    UI->>API: Create payment order
    API->>P: Validate cart
    P->>P: Check permission + amount limit
    P->>R: Create order (Test Mode)
    R-->>P: Razorpay order
    P->>DB: Store order + payment record
    P-->>UI: Checkout information

    C->>R: Complete payment
    R-->>UI: Payment response
    UI->>API: Payment details + signature
    API->>P: Verify signature
    P->>P: HMAC verification
    P->>DB: Mark order paid
    P->>DB: Write audit event
    P-->>UI: Payment success
```

---

# 🔁 Payment Failure and Retry

The system also supports a controlled failure path.

```text
Payment Attempt
      ↓
   Failed
      ↓
Record failure
      ↓
Increment retry count
      ↓
Audit event
      ↓
Can retry?
   ↙       ↘
 YES       NO
  ↓         ↓
New order   Stop
  ↓
Retry Checkout
```

The retry flow is capped at **3 attempts**.

The customer's cart/order context is preserved so a failed payment does not require rebuilding the entire shopping journey.

---

# 🧾 Audit Trail

Important events are recorded for merchant visibility.

Examples:

```text
product recommendation
upsell
cross-sell
checkout requested
checkout approved
checkout rejected
permission updated
payment order created
payment captured
payment failed
payment retried
payment refunded
invalid payment signature
workflow executed
```

The analytics service converts audit events into a visual timeline.

This supports the principle:

> **AI actions should be visible, bounded and auditable.**

---

# 📈 Revenue Analytics

The Phase 5 analytics service computes metrics from live MongoDB data.

Current dashboard metrics include:

- Total revenue
- Conversion rate
- Average order value
- Upsell revenue
- Cross-sell revenue
- Recommendation accuracy
- Workflow success rate
- Payment success rate
- Payment failure rate

### Analytics pipeline

```mermaid
flowchart TB
    A["Customer Sessions"] --> B["Recommendations"]
    B --> C["Cart Events"]
    C --> D["Orders"]
    D --> E["Payments"]

    B --> F["Recommendation Metrics"]
    C --> G["Conversion Metrics"]
    D --> H["Revenue Metrics"]
    E --> I["Payment Metrics"]

    F --> J["Merchant Analytics Dashboard"]
    G --> J
    H --> J
    I --> J
```

---

# 🧠 AI Architecture Engine

AI Commerce OS includes an architecture engine for workflow analysis.

The current pipeline contains seven conceptual steps:

```text
1. Task Analysis
       ↓
2. Structure Understanding
       ↓
3. Cognitive Module Selection
       ↓
4. Architecture Composition
       ↓
5. Workflow Generation
       ↓
6. Execution Planning
       ↓
7. Memory Optimisation
```

The engine can inspect workflow topology, identify required capabilities, describe execution plans, and use known patterns from AI memory.

---

# 🧩 Workflow Builder

The platform includes a visual workflow system.

Available concepts include:

```text
Start
End
AI Prompt
Product Search
Product Compare
Recommendation
Upsell
Cross-sell
Condition
Permission Gate
Human Approval
Cart
Checkout
Delay
```

Example commerce workflow:

```text
START
  ↓
Customer Request
  ↓
Product Search
  ↓
Recommendation
  ↓
Upsell
  ↓
Cross-sell
  ↓
Cart
  ↓
Permission Gate
  ↓
Human Approval
  ↓
Checkout
  ↓
END
```

---

# 🗂️ Project Structure

```text
ai-commerce-os/
│
├── app.py
├── config.py
├── db.py
├── models.py
├── auth.py
├── security.py
├── security_ext.py
├── routes.py
├── utils.py
│
├── ai/
│   ├── ai_routes.py
│   ├── provider_service.py
│   └── provider_adapters.py
│
├── agent/
│   ├── architecture_engine.py
│   └── memory_service.py
│
├── catalog/
│   ├── product_routes.py
│   ├── product_service.py
│   └── import_service.py
│
├── commerce/
│   ├── chat_service.py
│   ├── search_service.py
│   ├── recommendation_service.py
│   ├── comparison_service.py
│   ├── cart_service.py
│   ├── approval_service.py
│   ├── copilot_service.py
│   ├── language_service.py
│   └── commerce_routes.py
│
├── permissions/
│   ├── permission_routes.py
│   └── permission_service.py
│
├── workflow/
│   ├── workflow_service.py
│   ├── workflow_routes.py
│   ├── execution_engine.py
│   ├── node_handlers.py
│   └── template_service.py
│
├── payments/
│   ├── razorpay_client.py
│   ├── payment_service.py
│   ├── payment_routes.py
│   └── webhook_service.py
│
├── analytics/
│   ├── analytics_service.py
│   └── analytics_routes.py
│
├── templates/
│   ├── index.html
│   ├── chat.html
│   ├── products.html
│   ├── cart.html
│   ├── payments.html
│   ├── analytics.html
│   ├── dashboard.html
│   ├── permissions.html
│   ├── workflows.html
│   ├── builder.html
│   └── ...
│
├── static/
│   ├── app.js
│   ├── chat.js
│   ├── cart.js
│   ├── payments.js
│   ├── products.js
│   ├── dashboard.css
│   └── ...
│
├── requirements.txt
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── DEPLOY.md
└── README.md
```

---

# 🛠️ Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python + Flask |
| Database | MongoDB / MongoDB Atlas |
| Database Driver | PyMongo |
| Authentication | JWT |
| Password Security | bcrypt |
| Encryption | cryptography / Fernet |
| AI Layer | Provider adapter architecture |
| Commerce | Custom Python services |
| Payments | Razorpay REST API |
| Frontend | HTML, CSS, JavaScript |
| Deployment | Gunicorn / Docker |
| Testing | Python test modules |

---

# ⚙️ Installation

## Requirements

- Python 3.10+ recommended for the current development environment
- MongoDB local installation **or MongoDB Atlas**
- Internet connection for real Razorpay Test Mode API calls
- Optional AI provider credentials depending on the configured AI provider

---

## 1. Clone the repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd ai-commerce-os
```

---

## 2. Create a virtual environment

### Windows

```cmd
python -m venv venv
venv\Scripts\activate
```

### Linux / macOS

```bash
python -m venv venv
source venv/bin/activate
```

---

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

# 🔐 Environment Configuration

Create a file named:

```text
.env
```

Do **not** commit this file to GitHub.

Example:

```env
SECRET_KEY=your-long-random-secret

MONGO_URI=mongodb+srv://USERNAME:PASSWORD@YOUR_CLUSTER.mongodb.net/?retryWrites=true&w=majority
MONGO_DB_NAME=ai_commerce_os

JWT_ACCESS_SECRET=your-access-secret
JWT_REFRESH_SECRET=your-refresh-secret

API_KEY_ENCRYPTION_KEY=

RAZORPAY_KEY_ID=rzp_test_your_key_id
RAZORPAY_KEY_SECRET=your_test_secret
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret

AI_PROVIDER=mock

FEATURE_AI_ENGINE_ENABLED=true
FEATURE_PAYMENTS_ENABLED=true
FEATURE_WORKFLOW_BUILDER_ENABLED=true
```

Use the exact MongoDB Atlas connection string generated by Atlas.

Use only **Razorpay Test Mode** credentials during development.

### Never commit:

```text
.env
MongoDB passwords
Razorpay secrets
AI API keys
JWT secrets
```

The repository should contain `.env.example`, not the real `.env`.

---

# ▶️ Run the Application

```bash
python app.py
```

The Flask server runs on:

```text
http://localhost:5000
```

Health endpoint:

```text
GET /api/health
```

Expected response:

```json
{
  "success": true,
  "status": "ok",
  "service": "ai-commerce-os",
  "phase": 5
}
```

---

# 🧪 Testing

The project contains phase-specific tests:

```text
test_phase2.py
test_phase3.py
test_phase4.py
test_phase5.py
```

Run:

```bash
python -m pytest
```

or, depending on the local setup:

```bash
python test_phase5.py
```

---

# 🎬 5-Minute Demo Flow

For a buildathon demonstration, use one continuous customer journey.

```text
00:00  Problem + product introduction
00:30  Customer starts conversation
01:00  AI understands requirement
01:30  Product recommendation
02:00  Upsell + cross-sell
02:30  Cart creation
03:00  Permission / limit / confirmation
03:30  Demo or Razorpay Test Mode checkout
04:00  Payment result + audit trail
04:30  Revenue analytics
04:50  Final value proposition
```

### Suggested customer prompt

```text
I need a laptop for programming under ₹60,000.
```

Then demonstrate:

```text
Recommendation
      ↓
Upsell
      ↓
Cross-sell
      ↓
Cart
      ↓
Permission
      ↓
Confirmation
      ↓
Checkout
      ↓
Payment
      ↓
Audit
      ↓
Analytics
```

---

# 🏆 Why This Fits Track 01

AI Commerce OS directly targets AI Growth & Agentic Commerce through:

### 1. AI-powered product discovery

The agent understands customer requirements conversationally.

### 2. Revenue growth

Upselling and cross-selling create opportunities to increase order value.

### 3. Agentic commerce

The agent can coordinate multiple steps from discovery toward checkout.

### 4. Bounded financial actions

Payment actions are protected by permissions, limits and approval logic.

### 5. Explainability and auditability

Important actions are recorded so merchants can inspect what happened.

### 6. Failure handling

Payment failures are recorded and can enter a controlled retry flow.

### 7. Measurable business impact

Revenue, conversion, AOV, upsell, cross-sell and payment metrics are surfaced to the merchant.

---

# 🔒 Security Principles

AI Commerce OS follows several important security principles:

```text
Deny by default
      ↓
Least privilege
      ↓
Permission check
      ↓
Amount limit
      ↓
Customer confirmation
      ↓
Server-side amount calculation
      ↓
Payment signature verification
      ↓
Audit logging
```

The server calculates the final cart amount instead of trusting a client-provided amount.

Razorpay payment signatures are verified before an order is marked as paid.

---

# 🌐 API Modules

Major API areas include:

```text
/api/auth/*
/api/merchant/*
/api/products/*
/api/ai/*
/api/permissions/*
/api/workflows/*
/api/executions/*
/api/chat/*
/api/search/*
/api/compare/*
/api/recommend/*
/api/cart/*
/api/approval/*
/api/payments/*
/api/orders/*
/api/analytics/*
```

The exact route set is implemented by the corresponding Flask blueprints in the repository.

---

# 🗃️ MongoDB Data Model

The application uses merchant-scoped collections.

Major collections include:

```text
users
merchants
sessions
api_keys
audit_logs

products
ai_providers
permissions

workflows
workflow_versions
workflow_executions
templates
ai_memory

carts
conversations
recommendations
approvals
customer_sessions

orders
payments
webhooks
analytics
merchant_usage
```

Merchant IDs are used throughout the data layer to keep commerce data separated between merchants.

---

# 💡 Example Business Scenario

### Customer

```text
"I need a laptop for coding under ₹60,000."
```

### AI

```text
I found 3 matching laptops.
The best match has 16GB RAM and a high-performance processor.
```

### Cross-sell

```text
Would you like to add a wireless mouse?
```

### Cart

```text
Laptop + Mouse
Total: ₹XX,XXX
```

### Control

```text
Payment capability
      ↓
Permission check
      ↓
Amount limit
      ↓
Customer confirmation
```

### Transaction

```text
Checkout
   ↓
Razorpay Test Mode / Demo Mode
   ↓
Payment verification
```

### Merchant

```text
Revenue
Conversion
AOV
Upsell
Cross-sell
Payment success/failure
Audit timeline
```

---

# ⚠️ Demo Payment Note

When Razorpay Test Mode credentials are configured, the payment client is designed to make real Test Mode API requests.

When the Razorpay secret is absent, the application has a demo/mock path so the rest of the payment lifecycle can be exercised during development.

Therefore:

> **Demo/mock payment ≠ real Razorpay transaction.**

For a final buildathon demonstration, configure Razorpay Test Mode credentials if you want to demonstrate an actual Razorpay Test Mode checkout.

---

# 🚀 Future Roadmap

Potential future improvements include:

- deeper LLM-based intent understanding
- richer personalized recommendations
- MongoDB aggregation pipelines for analytics
- advanced merchant growth optimization
- campaign orchestration
- better AI memory
- automated experiment generation
- deeper Razorpay webhook reconciliation
- production observability
- stronger fraud/risk controls
- multi-agent commerce workflows

---

# 👨‍💻 Project Vision

AI Commerce OS is built around a simple principle:

```text
AI should not just talk.

AI should understand.
AI should recommend.
AI should act.
AI should stay within boundaries.
AI should explain what it did.
AI should leave an audit trail.
And AI should create measurable business value.
```

---

## ⭐ Final Positioning

> **AI Commerce OS — an agentic commerce platform that turns customer conversations into bounded, explainable and auditable transactions while helping merchants grow revenue.**

**Built for the Razorpay AI Buildathon 2026 — Track 01: AI Growth & Agentic Commerce.**
