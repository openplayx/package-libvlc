import Cocoa
import FlutterMacOS

@main
class AppDelegate: FlutterAppDelegate {
  // Without an active CoreAudio stream (e.g. --aout=afile or video-only
  // media), macOS App Nap coalesces timers to ~10 Hz after ~30-40 s of no user
  // input, causing libVLC's vout thread to drop ~15-20 fps (ALL-371).
  private var activity: NSObjectProtocol?

  override func applicationDidFinishLaunching(_ notification: Notification) {
    activity = ProcessInfo.processInfo.beginActivity(
      options: [.userInitiated, .latencyCritical],
      reason: "Disable App Nap and timer coalescing during video playback tests"
    )
    super.applicationDidFinishLaunching(notification)
  }

  override func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
    return true
  }

  override func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
    return true
  }
}
