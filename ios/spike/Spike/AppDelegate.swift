// Step 0 of docs/IOS-PLAN.md: a throwaway app that proves the tool chain and answers the plan's open questions on the
// real iPad: does the web UI run in a WKWebView, does the Local Network question come up, does music play on with the
// screen locked (Apple's player, and the page's own player), and does Apple's player take the server's live music
// conversion (/api/files/{id}/audio, no Range support)? Everything it learns goes to the iPad's log, prefixed BAMSSPIKE.

import AVFoundation
import MediaPlayer
import UIKit
import WebKit

func log(_ s: String) {
    NSLog("BAMSSPIKE %@", s)
    DispatchQueue.main.async { Spy.shared.add(s) }
}

/** The last lines of the log, shown on the player screen too (no PC needed to read them). */
final class Spy {
    static let shared = Spy()
    var lines: [String] = []
    var changed: (() -> Void)?
    func add(_ s: String) {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        lines.append("\(f.string(from: Date())) \(s)")
        if lines.count > 300 { lines.removeFirst(lines.count - 300) }
        changed?()
    }
}

@main
class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        do {
            try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
            log("audio session: playback")
        } catch {
            log("audio session failed: \(error)")
        }
        let w = UIWindow(frame: UIScreen.main.bounds)
        w.rootViewController = UINavigationController(rootViewController: WebController())
        w.makeKeyAndVisible()
        window = w
        log("started, iOS \(UIDevice.current.systemVersion)")
        return true
    }

    func applicationDidEnterBackground(_ application: UIApplication) { log("app: background") }
    func applicationWillEnterForeground(_ application: UIApplication) { log("app: foreground") }
}

// MARK: - the web UI

final class WebController: UIViewController, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler, UITextFieldDelegate {
    private var web: WKWebView!
    private let address = UITextField()
    static let key = "server"

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = UIColor(red: 0.06, green: 0.07, blue: 0.09, alpha: 1)
        title = "BAMS step 0"

        address.placeholder = "http://<server address>:8485"
        address.text = UserDefaults.standard.string(forKey: Self.key)
        address.borderStyle = .roundedRect
        address.autocapitalizationType = .none
        address.autocorrectionType = .no
        address.keyboardType = .URL
        address.returnKeyType = .go
        address.delegate = self
        address.frame = CGRect(x: 0, y: 0, width: 420, height: 32)
        navigationItem.titleView = address
        navigationItem.leftBarButtonItem = UIBarButtonItem(title: "Go", style: .plain, target: self, action: #selector(go))
        navigationItem.rightBarButtonItem = UIBarButtonItem(title: "Player test", style: .plain, target: self, action: #selector(player))

        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true
        config.mediaTypesRequiringUserActionForPlayback = []
        if #available(iOS 15.4, *) { config.preferences.isElementFullscreenEnabled = true }
        config.applicationNameForUserAgent = "BAMS-iOS/0.0.1"
        // the page's console and errors in the iPad's log
        let console = """
        (function(){
          var post = function(level, args){ try { window.webkit.messageHandlers.console.postMessage(level + ': ' +
            Array.prototype.map.call(args, function(a){ try { return typeof a === 'string' ? a : JSON.stringify(a) } catch(e) { return String(a) } }).join(' ')) } catch(e) {} };
          ['log','info','warn','error'].forEach(function(l){ var o = console[l]; console[l] = function(){ post(l, arguments); o.apply(console, arguments) } });
          window.addEventListener('error', function(e){ post('uncaught', [e.message + ' at ' + e.filename + ':' + e.lineno]) });
          window.addEventListener('unhandledrejection', function(e){ post('unhandled rejection', [String(e.reason)]) });
          document.addEventListener('play', function(e){ post('media', ['play ' + (e.target.currentSrc || e.target.src)]) }, true);
          document.addEventListener('ended', function(e){ post('media', ['ended ' + (e.target.currentSrc || e.target.src)]) }, true);
          document.addEventListener('error', function(e){ if (e.target && e.target.tagName && /AUDIO|VIDEO/.test(e.target.tagName)) post('media', ['error ' + (e.target.error && e.target.error.code) + ' ' + e.target.currentSrc]) }, true);
          post('page', ['MediaSource: ' + ('MediaSource' in window) + ', mediaSession: ' + ('mediaSession' in navigator)]);
        })();
        """
        config.userContentController.addUserScript(WKUserScript(source: console, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        config.userContentController.add(self, name: "console")

        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.allowsBackForwardNavigationGestures = true
        web.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(web)
        NSLayoutConstraint.activate([
            web.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            web.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            web.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            web.trailingAnchor.constraint(equalTo: view.trailingAnchor),
        ])
        if address.text?.isEmpty == false { go() }
    }

    func textFieldShouldReturn(_ textField: UITextField) -> Bool {
        go()
        return true
    }

    @objc func go() {
        address.resignFirstResponder()
        guard let text = address.text?.trimmingCharacters(in: .whitespaces), let url = URL(string: text), url.scheme != nil else {
            log("not an address: \(address.text ?? "")")
            return
        }
        UserDefaults.standard.set(text, forKey: Self.key)
        // the app's own request (the Local Network question is about the app; the page's requests may not ask)
        var req = URLRequest(url: url.appendingPathComponent("api/hello"), timeoutInterval: 8)
        req.setValue("BAMS-iOS/0.0.1", forHTTPHeaderField: "User-Agent")
        URLSession.shared.dataTask(with: req) { data, resp, err in
            if let err = err { log("hello failed: \(err.localizedDescription)") }
            else { log("hello \((resp as? HTTPURLResponse)?.statusCode ?? 0): \(String(data: data ?? Data(), encoding: .utf8)?.prefix(200) ?? "")") }
        }.resume()
        web.load(URLRequest(url: url))
        log("loading \(url)")
    }

    @objc func player() {
        navigationController?.pushViewController(PlayerTest(web: web), animated: true)
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        log("page \(message.body)")
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { log("page loaded: \(webView.url?.absoluteString ?? "")") }
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { log("page failed: \(error)") }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        log("page didn't load: \(error)")
    }
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        log("page process died, reloading")
        webView.reload()
    }

    // target="_blank": the server's own pages here, others in the browser
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url {
            if url.host == webView.url?.host { webView.load(navigationAction.request) }
            else { UIApplication.shared.open(url) }
            log("new window: \(url)")
        }
        return nil
    }
}

// MARK: - Apple's player

/** Plays files from the signed-in server in AVQueuePlayer, through media-ticket links (the player has no cookie), with
 *  Now Playing and the lock screen's buttons: the originals (/stream) or the live conversion (/audio). */
final class PlayerTest: UIViewController {
    private let web: WKWebView
    private let ids = UITextField()
    private let text = UITextView()
    private let player = AVQueuePlayer()
    private var observers: [NSKeyValueObservation] = []
    private var titles: [AVPlayerItem: String] = [:]
    private var timer: Timer?

    init(web: WKWebView) {
        self.web = web
        super.init(nibName: nil, bundle: nil)
    }
    required init?(coder: NSCoder) { fatalError() }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        title = "Player test"
        ids.placeholder = "file ids, e.g. 12, 13, 14"
        ids.borderStyle = .roundedRect
        ids.keyboardType = .numbersAndPunctuation
        ids.text = UserDefaults.standard.string(forKey: "ids")
        let buttons = UIStackView(arrangedSubviews: [
            button("Originals (/stream)") { [weak self] in self?.play("stream") },
            button("Converted (/audio)") { [weak self] in self?.play("audio") },
            button("Pause/Play") { [weak self] in self?.toggle() },
            button("Next") { [weak self] in self?.player.advanceToNextItem() },
            button("Clear log") { Spy.shared.lines = []; Spy.shared.changed?() },
        ])
        buttons.spacing = 12
        buttons.distribution = .fillEqually
        text.isEditable = false
        text.font = .monospacedSystemFont(ofSize: 12, weight: .regular)
        let stack = UIStackView(arrangedSubviews: [ids, buttons, text])
        stack.axis = .vertical
        stack.spacing = 12
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 12),
            stack.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -12),
            stack.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 16),
            stack.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -16),
        ])
        Spy.shared.changed = { [weak self] in
            self?.text.text = Spy.shared.lines.joined(separator: "\n")
            self?.text.scrollRangeToVisible(NSRange(location: (self?.text.text.count ?? 1) - 1, length: 1))
        }
        Spy.shared.changed?()
        remote()
        NotificationCenter.default.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main) { n in
            log("audio interruption: \(n.userInfo ?? [:])")
        }
        NotificationCenter.default.addObserver(forName: AVAudioSession.routeChangeNotification, object: nil, queue: .main) { [weak self] n in
            let why = (n.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt).flatMap(AVAudioSession.RouteChangeReason.init)
            log("route change: \(String(describing: why))")
            if why == .oldDeviceUnavailable { self?.player.pause() }  // headphones out
        }
        NotificationCenter.default.addObserver(forName: .AVPlayerItemDidPlayToEndTime, object: nil, queue: .main) { [weak self] n in
            log("ended: \(self?.titles[n.object as! AVPlayerItem] ?? "?")")
        }
        observers.append(player.observe(\.currentItem, options: [.new]) { [weak self] p, _ in
            DispatchQueue.main.async { self?.nowPlaying() }
        })
        observers.append(player.observe(\.timeControlStatus, options: [.new]) { p, _ in
            log("player: \(["paused", "waiting", "playing"][p.timeControlStatus.rawValue]) \(p.reasonForWaitingToPlay?.rawValue ?? "")")
        })
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.nowPlaying() }
    }

    private func button(_ title: String, _ action: @escaping () -> Void) -> UIButton {
        let b = UIButton(type: .system)
        b.setTitle(title, for: .normal)
        b.addAction(UIAction { _ in action() }, for: .touchUpInside)
        return b
    }

    /** The ticket prefix from the signed-in page, then the queue. */
    private func play(_ kind: String) {
        let list = (ids.text ?? "").split(whereSeparator: { ",; ".contains($0) }).compactMap { Int($0) }
        UserDefaults.standard.set(ids.text, forKey: "ids")
        guard !list.isEmpty, let origin = web.url.flatMap({ u -> String? in
            guard let s = u.scheme, let h = u.host else { return nil }
            return "\(s)://\(h)\(u.port.map { ":\($0)" } ?? "")"
        }) else {
            log("type file ids, and open the server first")
            return
        }
        web.callAsyncJavaScript("const r = await fetch('/api/media-ticket'); return (await r.json()).prefix", arguments: [:],
                                in: nil, in: .page) { [weak self] result in
            guard let self = self else { return }
            switch result {
            case .failure(let e): log("ticket failed: \(e)")
            case .success(let v):
                guard let prefix = v as? String else { log("no ticket: \(v)"); return }
                self.player.removeAllItems()
                self.titles = [:]
                for id in list {
                    guard let url = URL(string: "\(origin)\(prefix)/files/\(id)/\(kind)") else { continue }
                    let item = AVPlayerItem(url: url)
                    self.titles[item] = "\(kind) \(id)"
                    self.observers.append(item.observe(\.status, options: [.new]) { it, _ in
                        let name = "\(kind) \(id)"
                        switch it.status {
                        case .readyToPlay: log("ready: \(name), \(Int(it.duration.seconds.isFinite ? it.duration.seconds : -1)) s")
                        case .failed: log("FAILED: \(name): \(it.error.map { "\($0)" } ?? "?") \(it.errorLog()?.events.last?.errorComment ?? "")")
                        default: break
                        }
                    })
                    self.player.insert(item, after: nil)
                }
                log("queued \(list.count) (\(kind)) from \(origin)")
                self.player.play()
            }
        }
    }

    private func toggle() {
        if player.timeControlStatus == .paused { player.play() } else { player.pause() }
    }

    private func nowPlaying() {
        guard let item = player.currentItem else {
            MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
            return
        }
        var info: [String: Any] = [
            MPMediaItemPropertyTitle: titles[item] ?? "BAMS",
            MPMediaItemPropertyArtist: "BAMS step 0",
            MPNowPlayingInfoPropertyElapsedPlaybackTime: item.currentTime().seconds,
            MPNowPlayingInfoPropertyPlaybackRate: player.rate,
        ]
        if item.duration.seconds.isFinite { info[MPMediaItemPropertyPlaybackDuration] = item.duration.seconds }
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
    }

    private func remote() {
        let c = MPRemoteCommandCenter.shared()
        c.playCommand.addTarget { [weak self] _ in log("remote: play"); self?.player.play(); return .success }
        c.pauseCommand.addTarget { [weak self] _ in log("remote: pause"); self?.player.pause(); return .success }
        c.togglePlayPauseCommand.addTarget { [weak self] _ in log("remote: toggle"); self?.toggle(); return .success }
        c.nextTrackCommand.addTarget { [weak self] _ in log("remote: next"); self?.player.advanceToNextItem(); return .success }
        c.changePlaybackPositionCommand.addTarget { [weak self] e in
            guard let e = e as? MPChangePlaybackPositionCommandEvent else { return .commandFailed }
            log("remote: seek \(Int(e.positionTime))")
            self?.player.seek(to: CMTime(seconds: e.positionTime, preferredTimescale: 600))
            return .success
        }
    }
}
