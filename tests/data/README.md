# tests/data — Test Fixtures

> **Do not delete these files.** They are the test data for `psse_model_util` unit and integration tests.

---

## Files

### ModelComparison test pair

| File | Description |
|------|-------------|
| `Model_1.raw` | Synthetic PSS/E v34 RAW model — baseline. Used as `model1` in `ModelComparison` tests. |
| `Model_2.raw` | Synthetic PSS/E v34 RAW model — intentionally modified from `Model_1`. Used as `model2`. |
| `Model_1 and 2 differences.txt` | Full documented list of every intentional difference between `Model_1` and `Model_2`. Use this as the ground truth when writing or verifying `ModelComparison` test assertions. |
| `Model_1.raw.txt` | Text copy of `Model_1.raw` (plain text, same content — for inspection without a PSS/E viewer). |
| `Model_2.raw.txt` | Text copy of `Model_2.raw`. |

**Differences between Model_1 and Model_2 include:**

- Bus number changes (101→111, 213→219, 3001→3111)
- Bus name changes (bus 201: HYDRO→HHHHH)
- Bus parameter changes (baskv, vm, va, nvhi, nvlo, evhi, evlo)
- Bus additions (161, 156, 210) and deletions (3010, 2000, 2001)
- Load changes: id changes, stat changes, electrical parameter changes, additions, deletions
- Fixed shunt changes: bus/id changes, electrical parameter changes, additions
- Generator changes: bus/id changes, electrical parameter changes, additions, deletions
- AC line changes: bus number changes, topology changes (split, merge, removal, addition)
- Transformer changes: bus number changes, name changes, electrical parameter changes, 3W→2W and 2W→3W conversions
- Switched shunt changes: electrical parameter changes, addition

### v34 RAW samples

| File | Description |
|------|-------------|
| `sample_34.raw` | Minimal PSS/E v34 RAW file. Primary sample for unit tests of the RAW parser. |
| `sample2_34.raw` | Second minimal v34 RAW file. Use for multi-file or regression tests. |

### v35 RAW/RAWX samples

| File | Description |
|------|-------------|
| `sample_v35.raw` | Minimal PSS/E v35 RAW file. Use to test v35-specific parsing paths. |
| `sample_v35.rawx` | Minimal PSS/E v35 RAWX (JSON) file. Use to test the RAWX load path. |
| `sample2_v35.rawx` | Second minimal v35 RAWX file. |

### Targeted test cases

| File | Description |
|------|-------------|
| `transformer.raw` | RAW file with transformer-heavy content. Use for transformer parsing / multi-row record tests. |
| `minimal.raw` | Smallest valid RAW file. Use for edge-case / empty-section handling tests. |

### Sequence files

| File | Description |
|------|-------------|
| `sample.seq` | Sample PSS/E sequence file (harmonics/SEQ format). Not yet used in tests. |
| `example.seq` | Example sequence file. Not yet used in tests. |

### Results reference

| File | Description |
|------|-------------|
| `results.txt` | Reference output from prior runs. Used for regression validation. |

---

## Usage in Tests

```python
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# ModelComparison test pair
MODEL_1 = DATA_DIR / "Model_1.raw"
MODEL_2 = DATA_DIR / "Model_2.raw"

# Version-specific samples
SAMPLE_V34 = DATA_DIR / "sample_34.raw"
SAMPLE_V35_RAW = DATA_DIR / "sample_v35.raw"
SAMPLE_V35_RAWX = DATA_DIR / "sample_v35.rawx"
```
