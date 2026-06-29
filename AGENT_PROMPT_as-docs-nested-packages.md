# Agent Task: Add Nested Package Support to as-docs

## Objective
Enhance as-docs v0.1.0 to recursively discover and document POUs (Program Organization Units) in nested Automation Studio packages, specifically in the `Infrastructure/` folder structure and other nested package hierarchies.

---

## Current Problem

### Limitation
as-docs v0.1.0 only scans top-level directories:
- ✅ `Logical/` (top-level POUs)
- ✅ `Logical/Libraries/` (when `scan_libraries: true`)
- ❌ `Logical/Infrastructure/` (nested packages - **NOT scanned**)
- ❌ `Logical/Infrastructure/Alarms/` (nested sub-packages - **NOT scanned**)
- ❌ `Logical/Infrastructure/Charts/` (nested sub-packages - **NOT scanned**)

### Evidence from Real Project
**Project**: C:\100_Projects\130_AS_6\SOMA\AS6_R1580_sendToBR_AI

**Project Structure**:
```
Logical/
  ├── Package.pkg                    (references Infrastructure package)
  ├── Global.var
  ├── Global.typ
  ├── Libraries/
  ├── mappView/
  └── Infrastructure/                (NESTED - NOT scanned)
      ├── Package.pkg                (defines sub-packages and POUs)
      ├── Alarms/
      │   ├── Package.pkg
      │   ├── AlarmProg/
      │   │   └── IEC.prg            (PROGRAM POU - NOT found)
      │   ├── BoolSubscription/
      │   │   └── IEC.prg            (PROGRAM POU - NOT found)
      │   └── StringSubscription/
      │       └── IEC.prg            (PROGRAM POU - NOT found)
      ├── Charts/
      │   ├── DryChart/
      │   │   └── IEC.prg
      │   ├── EnergyAir/
      │   │   └── IEC.prg
      │   └── ... (9 more Energy* POUs)
      ├── Wizard/
      │   ├── WizStMach/
      │   │   └── IEC.prg
      │   ├── WizSubs/
      │   │   └── IEC.prg
      │   └── ... (4 more Wizard POUs)
      ├── VizuControl/
      ├── AuxiliarySection/
      ├── BladeChamber/
      └── ... (8 more packages)
```

**Current Output**:
```
as-docs status
POUs: 2                           ← Should be 41+
Tasks: 0

POU freshness:
  ✅ Package: present
  ✅ IEC: present
  ❌ AlarmProg: missing
  ❌ BoolSubscription: missing
  ❌ StringSubscription: missing
  ❌ DryChart: missing
  ❌ EnergyAir: missing
  ❌ ... (33 more missing)
```

**Expected Output After Fix**:
```
as-docs status
POUs: 41+                         ← All Infrastructure POUs
Tasks: 0

POU freshness:
  ✅ Package: present
  ✅ IEC: present
  ✅ AlarmProg: present
  ✅ BoolSubscription: present
  ✅ StringSubscription: present
  ✅ DryChart: present
  ✅ EnergyAir: present
  ... (33 more present)
```

---

## Technical Root Cause

The scanner in as-docs only processes the top-level `Logical/Package.pkg` and doesn't recursively follow package references (`.pkg` files) into nested directories.

### Current Flow (Broken)
```
Logical/Package.pkg
├─ References: Libraries ✅ (scanned)
├─ References: mappView ✅ (scanned)
└─ References: Infrastructure ❌ (NOT recursed into)
    └─ Logical/Infrastructure/Package.pkg (NEVER READ)
        └─ Contains Alarms, Charts, Wizard, etc. (ALL MISSING)
```

### Expected Flow (After Fix)
```
Logical/Package.pkg
├─ References: Libraries ✅ (scanned)
├─ References: mappView ✅ (scanned)
└─ References: Infrastructure ✅ (RECURSIVELY SCANNED)
    └─ Logical/Infrastructure/Package.pkg ✅ (READ)
        ├─ References: Alarms ✅ (SCANNED)
        │   └─ Logical/Infrastructure/Alarms/Package.pkg ✅
        │       ├─ AlarmProg/IEC.prg ✅ (FOUND)
        │       ├─ BoolSubscription/IEC.prg ✅ (FOUND)
        │       └─ StringSubscription/IEC.prg ✅ (FOUND)
        ├─ References: Charts ✅ (SCANNED)
        │   └─ Logical/Infrastructure/Charts/Package.pkg ✅
        │       ├─ DryChart/IEC.prg ✅ (FOUND)
        │       ├─ EnergyAir/IEC.prg ✅ (FOUND)
        │       └─ ... (9 more) ✅
        └─ ... (more packages recursed)
```

---

## Implementation Requirements

### 1. **Modify Scanner Logic** (`as_docs/scanner.py` or equivalent)

#### Current Behavior (Pseudocode)
```python
def scan_logical_packages(logical_root):
    root_pkg = read_package_file(logical_root / "Package.pkg")
    for obj in root_pkg.objects:
        if obj.type == "Package":
            scan_directory(logical_root / obj.name)
        elif obj.type == "Program":
            scan_program(logical_root / obj.path)
    # STOPS HERE - does not recurse into nested packages
```

#### Required Behavior (Pseudocode)
```python
def scan_logical_packages(logical_root, visited=None):
    """Recursively scan package hierarchy with cycle detection."""
    if visited is None:
        visited = set()
    
    pkg_path = logical_root / "Package.pkg"
    if pkg_path in visited:
        return  # Prevent infinite recursion
    visited.add(pkg_path)
    
    root_pkg = read_package_file(pkg_path)
    for obj in root_pkg.objects:
        if obj.type == "Package":
            # FIX: Recurse into nested packages
            nested_path = logical_root / obj.name
            scan_logical_packages(nested_path, visited)  # ← RECURSIVE CALL
        elif obj.type == "Program":
            scan_program(logical_root / obj.path)
        elif obj.type == "Library":
            scan_library(logical_root / obj.path)
```

### 2. **Configuration YAML Support**

The `.as-docs.yaml` should recognize these new options:

```yaml
scanner:
  active_configuration: "OptimaMaster"
  
  # NEW OPTIONS for nested packages
  max_recursion_depth: 10            # prevent infinite recursion (default: 10)
  recursive_packages: true           # enable nested package scanning (default: true)
  package_cycle_detection: true      # track visited .pkg files (default: true)
  
  ignore_dirs:
    - Temp
    - Binaries
    - Diagnosis
  
  scan_libraries: true
  external_lib_prefixes:
    - "Mp"
    - "Mc"
    - "ACP10"
    - "Ar"
```

### 3. **Error Handling**

Implement robust error handling for:
- **Circular package references**: Detect and skip if `Package A → Package B → Package A`
- **Missing nested packages**: Log warnings if a `Package.pkg` references a non-existent subdirectory
- **Malformed `.pkg` files**: Gracefully handle XML parsing errors
- **Recursion depth limits**: Stop recursion if depth exceeds `max_recursion_depth`

### 4. **Logging & Diagnostics**

Add verbose logging to help debug nested package discovery:

```python
# Example debug output
[DEBUG] Scanning Logical/Package.pkg
[DEBUG] → Found package reference: Infrastructure
[DEBUG] → Recursing into Logical/Infrastructure/ (depth=1)
[DEBUG] Scanning Logical/Infrastructure/Package.pkg
[DEBUG] → Found package reference: Alarms
[DEBUG] → Recursing into Logical/Infrastructure/Alarms/ (depth=2)
[DEBUG] Scanning Logical/Infrastructure/Alarms/Package.pkg
[DEBUG] → Found program: AlarmProg
[DEBUG] → Found program: BoolSubscription
[DEBUG] ← Exiting Logical/Infrastructure/Alarms/ (depth=2)
[DEBUG] → Found package reference: Charts
[DEBUG] → Recursing into Logical/Infrastructure/Charts/ (depth=2)
...
[INFO] Discovery complete: 41 POUs, 8 packages, 5 libraries
```

---

## Testing Requirements

### Test Case 1: Simple Nested Package
**Structure**:
```
Logical/
├── Package.pkg (references: Libraries, NestedPackage)
└── NestedPackage/
    ├── Package.pkg (defines: MyProgram)
    └── MyProgram/
        └── IEC.prg
```

**Expected**: `MyProgram` should be discovered and documented.

### Test Case 2: Multi-Level Nesting
**Structure**:
```
Logical/
├── Package.pkg (references: Level1)
└── Level1/
    ├── Package.pkg (references: Level2)
    └── Level2/
        ├── Package.pkg (references: Level3)
        └── Level3/
            ├── Package.pkg (defines: MyProgram)
            └── MyProgram/
                └── IEC.prg
```

**Expected**: `MyProgram` at depth 3 should be discovered.

### Test Case 3: Real-World Infrastructure Package
**Structure**: Use the actual SOMA project structure (41 POUs across 8 nested packages)

**Expected**: All 41 Infrastructure POUs should be discovered and `as-docs status` should show:
```
POUs: 41+
```

### Test Case 4: Circular Reference Detection
**Structure**:
```
Logical/
├── Package.pkg (references: PackageA)
└── PackageA/
    ├── Package.pkg (references: PackageB)
    └── PackageB/
        └── Package.pkg (references: PackageA)  ← Circular!
```

**Expected**: Circular reference should be detected and logged, scanner should not hang.

### Test Case 5: Mixed Nested and Top-Level POUs
**Structure**:
```
Logical/
├── Package.pkg (references: Libraries, NestedPkg, defines: TopLevelProg)
├── TopLevelProg/
│   └── IEC.prg
└── NestedPkg/
    ├── Package.pkg (defines: NestedProg)
    └── NestedProg/
        └── IEC.prg
```

**Expected**: Both `TopLevelProg` and `NestedProg` should be discovered.

---

## Validation Checklist

- [ ] Recursive package scanning works for 3+ nesting levels
- [ ] `as-docs status` correctly reports all discovered POUs (no "missing" entries)
- [ ] `as-docs generate` produces markdown docs for all nested POUs
- [ ] Circular references are detected and don't cause hangs
- [ ] Recursion depth limit prevents stack overflow
- [ ] Configuration options work: `recursive_packages`, `max_recursion_depth`
- [ ] Backward compatible with flat package structures
- [ ] Verbose logging (`as-docs -v generate`) shows recursion flow
- [ ] Real-world test: SOMA project now shows 41+ POUs instead of 2
- [ ] Unit tests cover all nested package scenarios

---

## Expected Outcome

After implementation:
```bash
cd C:\100_Projects\130_AS_6\SOMA\AS6_R1580_sendToBR_AI
as-docs generate
as-docs status
```

**Current (Broken)**:
```
POUs: 2
POU freshness:
  ✅ Package: present
  ✅ IEC: present
  ❌ AlarmProg: missing
  ❌ BoolSubscription: missing
  ... (38 more missing)
```

**After Fix**:
```
POUs: 41
POU freshness:
  ✅ Package: present
  ✅ IEC: present
  ✅ AlarmProg: present
  ✅ BoolSubscription: present
  ✅ StringSubscription: present
  ✅ DryChart: present
  ✅ EnergyAir: present
  ✅ EnergyEletricity: present
  ✅ EnergyGas: present
  ✅ EnergyWaterFlow: present
  ✅ EnergyWaterPower: present
  ✅ SpeedChart: present
  ✅ SubsCharts: present
  ✅ ViscosityCharts: present
  ✅ AuxProg: present
  ✅ AuxSubscription: present
  ✅ BladeChamber: present
  ✅ BladeChamber1: present
  ✅ FactoryConfig: present
  ✅ ICMPping: present
  ✅ IecCheck: present
  ✅ VizuCrtl: present
  ✅ VizuSubs: present
  ✅ VisVizCrtl: present
  ✅ FlyingSleeve: present
  ✅ RecTransfer: present
  ✅ WizStMach: present
  ✅ WizSubs: present
  ✅ WizSubs_old: present
  ✅ WizVisCtrl: present
  ✅ Client: present
  ✅ SubsAlarms: present
  ✅ Recepty: present
  ✅ TestVars: present
  ✅ Password: present
  ✅ Password1: present
  ✅ Subscription: present
  ✅ Actions: present
  ... (all POUs present)
```

---

## Deliverables

1. **Modified as-docs source code** with recursive package support
2. **Updated `.as-docs.yaml` schema** documentation
3. **Unit tests** for all nested package scenarios
4. **Integration test** against the SOMA project (41 POUs)
5. **Verbose logging output** showing recursion flow
6. **Backward compatibility** verification with flat projects
7. **Release notes** documenting the new feature

---

## Priority
**HIGH** - This is a critical blocker for documenting enterprise AS projects with modular/nested package structures.

---

## References
- **Current Version**: as-docs v0.1.0
- **Test Project**: C:\100_Projects\130_AS_6\SOMA\AS6_R1580_sendToBR_AI
- **Source**: https://github.com/[as-docs-repo] (if public)
- **Issue**: Nested packages not recursively scanned during POU discovery
