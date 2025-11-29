# OCI-MCP-SmartQueryAI

**OCI-MCP-SmartQueryAI** is an AI-powered assistant that uses the **Model Context Protocol (MCP)** and **Generative AI (Ollama / OpenAI-compatible models)** to **orchestrate Oracle Cloud Infrastructure (OCI) resources using natural language**.

You can:

- Ask in plain English:  
  - “Get all instances from `test` compartment”  
  - “Create compute instance `SMARTVMTEST` in `root/test` using any subnet”  
  - “Terminate `AUTOTEST` instance in `test` compartment”
- Let the **planner LLM** generate an execution plan.
- Have the **MCP client** execute that plan using the **MCP server**, which talks to OCI via the official Python SDK.
- Use a **Streamlit UI** that looks similar to modern AI chat clients.

---

## 1. Features

- 🔹 **Natural language → OCI actions** via Ollama / LLM planner  
- 🔹 **MCP server** exposing OCI tools:
  - `get_compartment_ocid`
  - `list_instances`
  - `get_instance_by_name`
  - `get_available_subnets`
  - `get_subnet_by_name`
  - `get_latest_image_by_prefix`
  - `get_images_by_prefix`
  - `create_compute_instance`
  - `delete_instance`
- 🔹 **Smart planning** – planner decides which tools to call and how to chain them
- 🔹 **Streamlit UI** with console-like output
- 🔹 Designed to be **extensible** to more OCI services and even AWS in future

---

## 2. Repository Layout

```text
OCI-MCP-SmartQueryAI/
├── common/
│   └── utils.py
├── config/
│   └── settings.yaml           # OCI & app configuration (edit this)
├── docs/
│   └── architecture.md
├── mcp_server/
│   ├── mcp_oci_server.py       # FastAPI + MCP server for OCI tools
│   ├── oci_helper.py           # OCI SDK helper methods
│   └── tools/                  # MCP tool registration
├── mcp_client/
│   ├── mcp_client_helper.py    # MCP HTTP client wrapper
│   ├── streamlit_app.py        # (optional) Streamlit entrypoint
│   └── ollama/
│       ├── smart_ollama_mcp_client.py  # CLI AI planner client
│       └── planner_prompt.txt          # System prompt for planner LLM
├── scripts/
│   └── test_mcp_client.py      # Simple direct MCP client test
├── voice-assistant/
│   └── speech_to_text.py       # Future voice integration
├── control_services.sh         # Helper to start/stop MCP server + Streamlit UI
├── requirements.txt
└── README.md
```

---

## 3. Prerequisites

### 3.1. OS / Runtime

* Linux (tested on Oracle Linux / RHEL-like distros)
* Python **3.10+** (tested with 3.12)
* `bash` / POSIX shell (for `control_services.sh`)

### 3.2. OCI Setup

1. **OCI Config File**

Create / verify `~/.oci/config` with a profile (default: `DEFAULT`):

```ini
[DEFAULT]
user=ocid1.user.oc1..aaaaaaaa...
fingerprint=aa:bb:cc:dd:...
key_file=/home/<user>/.oci/oci_api_key.pem
tenancy=ocid1.tenancy.oc1..aaaaaaaa...
region=us-phoenix-1
```

2. **Policies / IAM**

The user (or group) associated with your config must have permissions similar to:

```text
Allow group <group-name> to inspect compartments in tenancy
Allow group <group-name> to read virtual-network-family in tenancy
Allow group <group-name> to inspect images in tenancy
Allow group <group-name> to manage instance-family in compartment <target-compartment-name>
```

Adjust scope (`tenancy` vs specific compartments) as per your governance model.

---

### 3.3. Ollama / LLM

Install and run **Ollama** on a machine reachable from the MCP client:

```bash
# On the Ollama host
curl -fsSL https://ollama.com/install.sh | sh        # or use the official installer
ollama serve                                        # typically listens on :11434

# Pull a suitable model (e.g., llama3.2)
ollama pull llama3.2
```

Then set in the environment (on the machine where you run the client / UI):

```bash
export OLLAMA_URL="http://<ollama-host>:11434/api/chat"
export OLLAMA_MODEL="llama3.2"
```

> You can swap in other chat-capable models as needed, as long as they support an OpenAI-style `/api/chat` interface via Ollama.

---

## 4. Clone & Install

```bash
# 1) Clone the repository
git clone https://github.com/bhaskaro/OCI-MCP-SmartQueryAI.git
cd OCI-MCP-SmartQueryAI

# 2) Create & activate virtual environment
python -m venv .venv
source .venv/bin/activate      # On Windows: .venv\Scripts\activate

# 3) Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4) Ensure Python can see this repo as a package
export PYTHONPATH="$(pwd)"
```

---

## 5. Configuration

### 5.1. `config/settings.yaml`

Update the configuration file to match your environment. A typical layout may include:

```yaml
oci:
  profile: DEFAULT           # profile from ~/.oci/config
  region: us-phoenix-1       # OCI region
  default_compartment: test  # logical name used by your helper / planner

server:
  host: 0.0.0.0
  port: 8000

streamlit:
  host: 0.0.0.0
  port: 8501
```

> Adjust keys/structure to match the current `settings.yaml` in the repo if it has changed.

Here is the **updated 5.2 Environment Variables section**, rewritten cleanly to match your new `.env`-based configuration model.
You can **copy and paste this directly into your README.md**.

---

### **5.2. Environment Variables**

The application now loads configuration from a **`.env` file** using `python-dotenv`.
This keeps sensitive values out of your source code and simplifies deployment.

#### **Step 1 — Create a `.env` file**

From the project root:

```bash
cd OCI-MCP-SmartQueryAI

cat > .env << 'EOF'
# LLM / Ollama
OLLAMA_URL=http://<ollama-host>:11434/api/chat
OLLAMA_MODEL=llama3.2

# MCP server
MCP_BASE_URL=http://localhost:8000/mcp

# (Optional) OCI config overrides
OCI_CONFIG_FILE=$HOME/.oci/config
OCI_PROFILE=DEFAULT
EOF
```

Or if you prefer using an example file:

```bash
cp .env.example .env
```
#### **Step 2 — Override per-session variables (optional)**

If you want to temporarily override values without editing `.env`:

```bash
export OLLAMA_URL=http://my-new-host:11434/api/chat
export OLLAMA_MODEL=llama3.2
export MCP_BASE_URL=http://localhost:8000/mcp
```

The application will prefer exported variables over `.env`.

---

## 6. Running the Stack

You have two options:

### 6.1. Using `control_services.sh` (recommended)

From the repo root:

```bash
chmod +x control_services.sh

# Start MCP server + Streamlit UI
./control_services.sh start

# Stop both
./control_services.sh stop

# Restart both
./control_services.sh restart
```

The script will:

* Start the **MCP OCI server** (FastAPI + MCP) on port `8000`.
* Start the **Streamlit UI** on port `8501`.

Logs typically go to:

* MCP server: `/tmp/mcp_server.log`
* UI: `/tmp/streamlit_ui.log`

### 6.2. Manual Start (advanced)

**MCP server:**

```bash
# From repo root, with venv activated and PYTHONPATH set
uvicorn mcp_server.mcp_oci_server:app --host 0.0.0.0 --port 8000
```

**Streamlit UI:**

```bash
# From repo root
streamlit run mcp_client/ollama/streamlit_ollama_ui.py \
  --server.address 0.0.0.0 \
  --server.port 8501
```

---

## 7. Firewall / Network (Oracle Linux example)

If you want to access the Streamlit UI remotely:

```bash
sudo firewall-cmd --add-port=8501/tcp --permanent
sudo firewall-cmd --reload

# (Similarly for MCP server if exposed remotely)
sudo firewall-cmd --add-port=8000/tcp --permanent
sudo firewall-cmd --reload
```

Then open in your browser:

* **Streamlit UI** → `http://<vm-ip>:8501/`

---

## 8. Testing via CLI (Smart Ollama MCP Client)

The AI planner client is in `mcp_client/ollama/smart_ollama_mcp_client.py`.

### 8.1. Basic pattern

From repo root (venv activated, PYTHONPATH set):

```bash
python -m mcp_client.ollama.smart_ollama_mcp_client "your natural language query here"
```

### 8.2. Examples

#### 8.2.1. List instances in a compartment

```bash
python -m mcp_client.ollama.smart_ollama_mcp_client \
  "get list of instances from test compartment"
```

Expected planner plan (simplified):

```json
{
  "steps": [
    {
      "tool": "get_compartment_ocid",
      "args": { "compartment_name": "test" },
      "save_as": "compartment_ocid"
    },
    {
      "tool": "list_instances",
      "args": { "compartment_ocid": "$compartment_ocid" },
      "save_as": "instances"
    }
  ]
}
```

The client will print:

* The generated plan
* Each MCP tool call
* Final variables, including `instances` with instance details.

---

#### 8.2.2. Create a compute instance

Example query:

```bash
python -m mcp_client.ollama.smart_ollama_mcp_client \
  "create compute instance with the name SMARTVMTEST in compartment root/test. \
   Take whatever subnet available in the same compartment."
```

Typical plan:

1. `get_compartment_ocid` → resolve `root/test`
2. `get_available_subnets` → pick a subnet in that compartment
3. `get_latest_image_by_prefix` → e.g., latest `oracle-linux` image
4. `create_compute_instance` → with resolved OCIDs and defaults:

   * shape: `VM.Standard.E2.1.Micro` (or as configured)
   * optional `cpu_mem_shape` for flex
   * subnet OCID
   * image OCID

---

#### 8.2.3. Get single instance details

```bash
python -m mcp_client.ollama.smart_ollama_mcp_client \
  "get AUTOTEST instance details from test compartment"
```

Planner should:

1. Resolve compartment OCID
2. Call `get_instance_by_name` (not `list_instances`)

---

#### 8.2.4. Terminate an instance

```bash
python -m mcp_client.ollama.smart_ollama_mcp_client \
  "terminate AUTOTEST instance in test compartment"
```

Planner should:

1. Resolve compartment OCID
2. `get_instance_by_name`
3. `delete_instance` (using `$instance.id`)

The underlying helper method will:

* Call `terminate_instance`
* Poll for `TERMINATED` state up to a configured timeout
* Return a structured result (e.g., `{ "instance_ocid": "...", "status": "TERMINATED" }`)

---

#### 8.2.5. Get latest image by prefix

```bash
python -m mcp_client.ollama.smart_ollama_mcp_client \
  "get latest image with prefix oracle-linux from compartment root"
```

Planner:

1. `get_compartment_ocid` for `root`
2. `get_latest_image_by_prefix` with `"oracle-linux"`

Helper:

* Uses `list_images` with `sort_by=TIMECREATED`, `sort_order=DESC`
* Filters by case-insensitive prefix
* Returns the newest matching image (id, name, time_created, lifecycle_state)

---

#### 8.2.6. Get all images by prefix

```bash
python -m mcp_client.ollama.smart_ollama_mcp_client \
  "get all images with prefix oracle-linux from compartment root"
```

Planner:

1. `get_compartment_ocid`
2. `get_images_by_prefix`

Helper uses `list_call_get_all_results` to fetch **all pages** and returns a list of all matching images.

---

## 9. Using the Streamlit UI

Once `control_services.sh` (or manual commands) have started the UI:

1. Open your browser to:
   `http://<vm-ip>:8501/`
2. You’ll see:

   * A **header** (e.g., “OCI-MCP SmartQueryAI Console”)
   * A **red horizontal line** under the header
   * A **text box** to enter your natural language query
   * A **Submit** button
   * A console-style area that prints:

     * Generated plan
     * Each MCP tool call
     * Final variables / results
   * A **footer** with another red line and a contact line (with email masked for privacy)

Example queries (same as CLI):

* `get list of instances from test compartment`
* `create compute instance with the name SMARTVMTEST in compartment root/test`
* `terminate AUTOTEST instance in test compartment`
* `get all images with prefix oracle-linux from compartment root`

---

## 10. Extensibility

OCI-MCP-SmartQueryAI is intentionally designed to be **open for extension**:

1. **Add new helper methods** in `mcp_server/oci_helper.py`
   (e.g., volumes, load balancers, object storage, Autonomous DB).
2. **Register them as MCP tools** in `mcp_server/mcp_oci_server.py`.
3. **Expose them to the planner** by updating `planner_prompt.txt` with:

   * tool name
   * arguments
   * behavior rules / when to use
4. Optionally adapt the planner prompt for:

   * AWS
   * multi-cloud scenarios
   * higher-order workflows (e.g., “clone this instance”, “snapshot then terminate”)

This makes the framework a solid base for **full AI-driven cloud orchestration**.

---

## 11. Safety Notes

* This tool can **create and destroy real OCI resources**.
* Always test in **non-production compartments** first.
* Consider adding:

  * “dry-run” mode
  * explicit confirmation for destructive operations (`delete_instance`, etc.)
  * logging / audit hooks

---
