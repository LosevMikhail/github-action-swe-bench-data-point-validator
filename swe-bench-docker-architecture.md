# SWE-bench Docker Architecture

This document describes **how SWE-bench applies patches, executes tests inside Docker containers, handles timeouts, parses outputs, and integrates validation**, with **explicit sources for each claim**.

---

## 1. Docker Architecture Overview

SWE-bench uses a multi-level Docker image hierarchy:
1. **Base image** – OS + language runtime
2. **Environment image** – system and language dependencies
3. **Instance image** – repository checkout at a fixed commit plus repo-specific build steps

This allows to reuse images.

---

## 2. Image Building Process

Docker images in SWE-bench are built at evaluation time. An image is built only if it does not already exist locally. This makes image building lazy and demand-driven.

A **Base image** is shared across many tasks. **Environment images** are shared across instance images. An **Instance image** can be reused if the repository and the base commit matches.

---

## 3. Test Execution Flow

### 3.1. Patch Application Process

Patch application occurs **after a container is created from an instance image** and **before any tests are executed**.

### How it works
1. The model’s output is written to a patch file in diff format.
2. The patch file is copied into the running container.
3. The harness attempts to apply the patch to the repository using `git apply` (with fallback strategies).
4. The repository is modified only within the container’s filesystem.

### Failure behavior
- If the patch does not apply cleanly:
  - Evaluation stops immediately
  - Tests are not executed
  - The instance is marked as a patch-application failure

### Important properties
- Patches are never baked into Docker images
- Each evaluation starts from a clean repository state
- Patch application happens at container runtime, not image build time

---

### 3.2. Test command execution with timeout handling

SWE-bench executes the repository’s native test command (e.g. `pytest`, `tox`, `npm test`). The exact command is defined per repository in the SWE-bench task specification.

### How the command is executed
1. The harness generates a shell script (commonly referred to as `eval.sh`)
2. The script assumes all dependencies are already installed
3. The script runs the test command
4. Output is wrapped with explicit markers for later parsing
5. The harness executes the script inside the container using Docker exec

### Timeout Purpose
Timeouts prevent:
- Hung test processes
- Unbounded resource usage
- Unfair evaluation conditions

### Timeout Enforcement mechanism
1. Test execution begins via Docker exec
2. The harness waits for completion up to a fixed timeout
3. If the timeout is exceeded:
   - The test process inside the container is forcibly terminated
   - Partial output is preserved
   - The instance is marked as timed out

---

### 3.4. Output Capture

### What is captured
- Standard output (stdout)
- Standard error (stderr)

### Where output goes
- Output is streamed from the container to the harness
- Logs are written verbatim to evaluation output files on the host

### Output structure
Test execution output is wrapped between explicit markers:

```
START_TEST_OUTPUT
<test runner output>
END_TEST_OUTPUT
```

These markers ensure reliable parsing across different test frameworks.

---

### 3.5. Output Parsing and Result Extraction

### Parsing process
1. The harness reads the saved test output logs
2. Known failure indicators are checked first:
   - Patch application failure
   - Timeout indicators
3. Output between the test markers is extracted
4. The extracted output is passed to a repository-specific parser

### Result determination
- All tests pass → instance marked **resolved**
- Any test fails → instance marked **unresolved**
- Output cannot be reliably parsed → instance marked **invalid**


---

### 3.6. Concrete Execution Scenarios

### Scenario A: Successful Fix
1. Container created from instance image
2. Patch applies cleanly
3. Tests run within the timeout
4. All tests pass
5. Output parsed successfully
6. Instance marked **resolved**

### Scenario B: Patch Does Not Apply
1. Container created
2. Patch application fails
3. Tests are skipped
4. Instance marked **failed (patch error)**

### Scenario C: Tests Fail
1. Patch applies successfully
2. Tests run
3. One or more tests fail
4. Output parsed
5. Instance marked **unresolved**

### Scenario D: Timeout
1. Patch applies successfully
2. Tests begin execution
3. Timeout is exceeded
4. Test process is terminated
5. Partial output is logged
6. Instance marked **timeout failure**

---

## 4. Integration Points

### 4.1. Validator Integration with Docker Infrastructure

The validator is a **part of the evaluation harness**, which orchestrates Docker execution and interprets the results. The validator decides whether a model-generated patch **successfully resolves** a task based **solely on test outcomes** produced inside Docker.

### Execution flow with validator integration

1. The harness creates a container from an instance image
2. Patch application and test execution occur inside Docker
3. Docker streams stdout/stderr back to the harness
4. The harness stores execution logs on the host
5. The validator logic parses the stored logs
6. A final evaluation result is computed

### Key integration properties

- Docker is treated as a **black-box execution engine**
- Validation is **purely post-execution analysis**
- Determinism is guaranteed by: immutable images, clean containers, consistent parsing rules

---

### 4.2. Data Point Requirements: When and Where Dependencies Are Installed

All dependency installation happens during Docker image build.

Dependencies are installed in **two distinct phases**, aligned with the image hierarchy.

#### Environment Image: Shared Dependency Installation

These dependencies are pre-defined, e.g. in `harness/constants/python.py`, in order to install them at this stage.

- Operating system packages (via `apt`)
- Language-level dependencies (e.g., Python packages via `pip` or `conda`)
- Build and test tooling required by multiple repositories

#### Instance Image: Repository-Specific Requirements

- Repository source code (cloned and checked out at a fixed commit)
- Repository-specific dependencies
- Repository build or setup commands (e.g., `pip install -e .`, `make`)

---

# Summary

SWE-bench is a feasible, correct and fast benchmark for evaluating large language models which is achieved using 3-layered Docker architecture.
