# W-Agent Python Trial Demo

This demo calls no-registration trial APIs. It does not require an API key,
account balance, or x402 wallet.

```bash
pip install requests
export GAIT_API_BASE_URL=https://www.w-agent.cn
```

图搜万物:

```bash
python3 trial_api_demo.py object-search /path/to/image.jpg --prompt "person"
```

Sequence parsing:

```bash
python3 trial_api_demo.py sequence-parse /path/to/sequence_frames
```

Gait Pose:

```bash
python3 trial_api_demo.py gait-pose /path/to/sequence_frames
```

Trial usage is limited by server-side IP/fingerprint quota configured in the
admin portal.
