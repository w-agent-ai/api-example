# Python Object Search API Demo

This package only demonstrates Object Search for registered users with an API Key.

## Setup

```bash
pip install requests
```

## Usage

1. Open `object_search_api_demo.py`.
2. Edit the top-level settings:
   - `API_KEY`: your W-Agent API Key.
   - `IMAGE_PATH`: local image path.
   - `PROMPT`: target description, for example `person`.
3. Run:

```bash
python3 object_search_api_demo.py
```

The script calls `POST /v1/object-search` and prints matching boxes plus billing information.
