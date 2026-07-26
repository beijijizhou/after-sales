# Batch Dieline Processing

Run from the project root:

```bash
.venv/bin/python -m automation.image_tools.batch_dieline \
  "/path/to/input-folder"
```

The output folder defaults to `<input-folder>_套刀模`. Existing output files
are skipped unless `--overwrite` is supplied.

Optional composition controls:

```bash
--zoom 1.1
--horizontal-shift 0
--vertical-shift 35
```

The relative input path must contain both the material and model. This prevents
the same phone model from using a dieline from the wrong material.

To rebuild the local dieline library from TIFF source files:

```bash
.venv/bin/python -m automation.image_tools.import_dielines \
  "/path/to/刀模数据"
```
