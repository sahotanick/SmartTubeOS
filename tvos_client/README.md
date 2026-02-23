# SmartTube tvOS Client (V1)

## Project
- Xcode project: `/Users/harnake/Documents/SmartTubeOS/tvos_client/SmartTubeTVOS.xcodeproj`
- Scheme: `SmartTubeTVOS`
- Target platform: tvOS simulator/device

## Companion URL
By default, client calls:
- `http://127.0.0.1:8000`

Override with environment variable at launch:
- `COMPANION_BASE_URL`

## Auto-start backend on app launch
When launching the `SmartTubeTVOS` scheme from Xcode, a launch pre-action runs:
- `/Users/harnake/Documents/SmartTubeOS/tvos_client/scripts/start_companion_backend.sh`

What it does:
- Starts backend only if `127.0.0.1:8000` is not already listening.
- Creates backend `.venv` and installs `requirements.txt` if needed.
- Loads backend env from `/Users/harnake/Documents/SmartTubeOS/tvos_companion_backend/.env.local` when present.
- Runs `uvicorn app.main:app` in background (`COMPANION_PROVIDER` from env/`.env.local`, fallback `mock`) bound to `0.0.0.0`.
- On each build, injects `CompanionAutoBaseURL=http://<your-mac-lan-ip>:8000` into the app bundle Info.plist for physical-device runs.

Routing behavior:
- tvOS simulator always uses `http://127.0.0.1:8000`.
- Physical Apple TV uses `COMPANION_BASE_URL` if provided, otherwise injected `CompanionAutoBaseURL`.

Backend launch log:
- `/Users/harnake/Documents/SmartTubeOS/tvos_companion_backend/.run/companion_backend.log`

## Build + tests
```bash
cd /Users/harnake/Documents/SmartTubeOS/tvos_client
xcodegen generate
xcodebuild -project SmartTubeTVOS.xcodeproj -scheme SmartTubeTVOS -destination 'platform=tvOS Simulator,name=Apple TV 4K (3rd generation),OS=26.2' test
```

## V1 feature coverage in client
- Home/Search/Subscriptions/History tabs
- Sign-in controls and profile switching in Settings
- Video details with metadata + plain-text description
- Comments panel with load-more and replies
- AVPlayer playback via companion `video/{id}/playback`
