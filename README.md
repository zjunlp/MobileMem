# MobileMem Dataset Explorer

This local Web viewer supports both the checked-in sample data and the complete
MobileMem-Omni dataset from Hugging Face.

**MobileMem Dataset Explorer is open-source software released under the MIT
License.** You may use, modify, and redistribute its source code under the
terms of the license.

The default sample contains:

- `u0`, session `0_0`, question `0_q_0`
- `u10`, session `10_0`, question `10_q_826`

It contains only the 24 images referenced by those two sessions. The full
dataset and its source ZIP archives are intentionally excluded from Git, but
the viewer can read them directly after download.

## Requirements

- Python 3.10 or newer
- `pip` and Python's built-in `venv` module
- A modern browser such as Chrome, Edge, Firefox, or Safari
- About 50 MB of free disk space for sample mode, plus the Python virtual
  environment
- About 6.5 GB of additional disk space for the complete dataset
- Local port `8766` available, or another port supplied through `MEMWEB_PORT`

Node.js, a database, external services, and API keys are not required.

## Run on macOS or Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./run_local.sh
```

Open <http://127.0.0.1:8766>.

Set `MEMWEB_PORT` to use another port:

```bash
MEMWEB_PORT=9000 ./run_local.sh
```

## Run on Windows PowerShell

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python app\server.py
```

Open <http://127.0.0.1:8766>.

To use another port in PowerShell:

```powershell
$env:MEMWEB_PORT = "9000"
.\.venv\Scripts\python app\server.py
```

The server reads the sample JSON and image folders from this directory by
default. Set `MEMWEB_DATA_DIR` to browse a separate full-dataset directory.

## Download the full dataset

Install the Hugging Face CLI and download the complete dataset into the ignored
`full-dataset/MobileMem` directory:

```bash
python -m pip install --upgrade huggingface_hub
hf download zjunlp/MobileMem \
  --repo-type dataset \
  --local-dir full-dataset/MobileMem
```

The download directory is exactly the layout consumed by this viewer and is
ignored by Git. A complete download includes files such as:

```text
full-dataset/MobileMem/
├── omni/data.jsonl
├── omni/questions.jsonl
├── omni/image.zip
└── text/
```

Start the viewer against the downloaded directory:

```bash
MEMWEB_DATA_DIR="$PWD/full-dataset/MobileMem" ./run_local.sh
```

Open <http://127.0.0.1:8766>. The viewer automatically detects
`omni/data.jsonl`, `omni/questions.jsonl`, and `omni/image.zip`, and exposes all
20 users. Images are read directly from `image.zip` on demand, so the archive
does not need to be extracted.

On Windows PowerShell, use:

```powershell
$env:MEMWEB_DATA_DIR = "$PWD\full-dataset\MobileMem"
.\.venv\Scripts\python app\server.py
```

Dataset page and raw-data notes:
<https://huggingface.co/datasets/zjunlp/MobileMem>.

## Open source and license

The source code in this repository is open source under the [MIT License](LICENSE).
The MobileMem dataset is downloaded separately from Hugging Face and remains
subject to the terms published with the dataset.
