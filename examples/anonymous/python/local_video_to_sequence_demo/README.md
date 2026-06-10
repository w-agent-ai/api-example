# Anonymous Python Local Video-To-Sequence Demo

Input is a video file. The demo:

1. Runs local CPU person detection and tracking.
2. Writes one folder per detected person sequence.
3. Uploads each generated sequence folder to the public Sequence API.
4. Pays each anonymous parse call with x402.

Run:

```bash
pip install requests opencv-python numpy eth-account web3 'x402[evm]'
export GAIT_TEST_WALLET_PRIVATE_KEY='0x...'
export GAIT_API_BASE_URL='https://www.h-agent.ai/api'
python3 examples/anonymous/python/local_video_to_sequence_demo/local_video_to_sequence_x402_demo.py /path/to/video.mp4
```
