# PSCAD-Style Subcircuit Ports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make subcircuit packaging use explicit internal port nodes like PSCAD modules.

**Architecture:** Add a topological `SUBCIRCUIT_PORT` component type with one pin named `node`. Packaging converts each external boundary connection into a port node inside `SubcircuitDefinition`, connects the original internal pin to that port node, and gives the top-level subcircuit instance a matching external pin. Solver flattening maps each external subcircuit pin to the corresponding internal port node by bridge wires, while ignoring the port component as a solver device.

**Tech Stack:** Python dataclasses, PySide6 `QGraphicsItem`, unittest, existing `CircuitModel` and `SolverBuilder`.

---

### Task 1: Lock PSCAD-Style Port Semantics With Tests

**Files:**
- Modify: `tests/test_regressions.py`

- [ ] **Step 1: Write failing tests**

Add tests that create a small selected internal circuit, package it, and assert:
- packaged subcircuit definitions contain `SUBCIRCUIT_PORT` components;
- every external subcircuit pin has a same-named internal port node;
- the original internal component pin is wired to the internal port node;
- flattening removes the top-level subcircuit while keeping the external network connected through the internal port.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m unittest -v tests.test_regressions.RegressionTests.test_subcircuit_packaging_creates_internal_port_nodes tests.test_regressions.RegressionTests.test_subcircuit_flattening_maps_external_ports_to_internal_port_nodes
```

Expected: fail because `ComponentType.SUBCIRCUIT_PORT` does not exist and packaging still maps ports directly to internal component pins.

### Task 2: Add Internal Port Component Type

**Files:**
- Modify: `models/circuit_model.py`
- Modify: `models/component_lib.py`
- Modify: `ui/symbols/primitive_symbols.py`
- Modify: `ui/symbols/__init__.py`
- Modify: `ui/circuit_canvas.py`

- [ ] **Step 1: Implement minimal data and symbol support**

Add `ComponentType.SUBCIRCUIT_PORT = "PORT"`, define one pin `node`, empty parameters, registry metadata, and draw it as a small labeled port node. Make `ComponentGraphicsItem` small for this type and suppress the normal pin-dot duplication if needed.

- [ ] **Step 2: Run the failing tests**

Expected: tests progress from missing enum to packaging/flattening assertion failures.

### Task 3: Package Boundaries As Internal Port Nodes

**Files:**
- Modify: `models/circuit_model.py`

- [ ] **Step 1: Convert external connections into port nodes**

In `create_subcircuit_from_selection()`, create one internal `SUBCIRCUIT_PORT` component per boundary connection, add an internal wire from the port node to the original internal pin, and make `SubcircuitPort.internal_comp_id/internal_pin_name` point to the port node.

- [ ] **Step 2: Run the packaging test**

Expected: packaging test passes.

### Task 4: Flatten Through Port Nodes

**Files:**
- Modify: `core/solver_builder.py`

- [ ] **Step 1: Bridge external pins to internal port nodes**

When flattening a subcircuit instance, add bridge wires from each external connection on `SUB.Pn` to the remapped internal `PORT.node`; skip `SUBCIRCUIT_PORT` in solver component order.

- [ ] **Step 2: Run the flattening test**

Expected: flattening test passes and the flattened node map connects external components to the remapped internal port node.

### Task 5: Verify and Commit

**Files:**
- Test: all touched Python files and full unittest suite

- [ ] **Step 1: Compile touched files**

```powershell
python -m py_compile models\circuit_model.py models\component_lib.py core\solver_builder.py ui\circuit_canvas.py ui\symbols\__init__.py ui\symbols\primitive_symbols.py tests\test_regressions.py
```

- [ ] **Step 2: Run all tests**

```powershell
python -m unittest discover -v
```

- [ ] **Step 3: Commit**

```powershell
git add docs\superpowers\plans\2026-05-16-pscad-subcircuit-ports.md models\circuit_model.py models\component_lib.py core\solver_builder.py ui\circuit_canvas.py ui\symbols\__init__.py ui\symbols\primitive_symbols.py tests\test_regressions.py
git commit -m "feat: add pscad style subcircuit ports"
```
