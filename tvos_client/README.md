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
