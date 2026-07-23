/**
 * Two-click region selector for macOS.
 * Prints: x,y,w,h  (Quartz / screencapture -R coordinates, top-left origin)
 * Exit 0 on success, 1 on cancel (Esc).
 *
 * Build:  swiftc -O -o region_select RegionSelect.swift
 */

import Cocoa

/// Shared selection state across all displays.
final class SelectionState {
    static let shared = SelectionState()

    /// First corner in Quartz global coords (top-left origin), if set.
    var corner1Quartz: CGPoint? = nil
    var instruction: String = "Click first corner  ·  Esc to cancel"
    weak var delegate: AppDelegate?

    private init() {}
}

final class OverlayView: NSView {
    let screen: NSScreen
    var cursorLocal: NSPoint? = nil

    init(frame: NSRect, screen: NSScreen) {
        self.screen = screen
        super.init(frame: frame)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override var isFlipped: Bool { true }
    override var acceptsFirstResponder: Bool { true }

    /// Convert view-local point → Quartz global (top-left origin).
    private func localToQuartz(_ local: NSPoint) -> CGPoint {
        let frame = screen.frame
        // local is flipped: y measured from top of this screen
        let cocoa = NSPoint(
            x: frame.origin.x + local.x,
            y: frame.origin.y + frame.size.height - local.y
        )
        let maxY = NSScreen.screens.map { $0.frame.maxY }.max() ?? frame.maxY
        return CGPoint(x: cocoa.x, y: maxY - cocoa.y)
    }

    /// Convert Quartz global → view-local (or nil if not on this screen).
    private func quartzToLocal(_ q: CGPoint) -> NSPoint? {
        let frame = screen.frame
        let maxY = NSScreen.screens.map { $0.frame.maxY }.max() ?? frame.maxY
        let cocoa = NSPoint(x: q.x, y: maxY - q.y)
        // Inside this screen?
        if cocoa.x < frame.minX || cocoa.x > frame.maxX ||
            cocoa.y < frame.minY || cocoa.y > frame.maxY {
            return nil
        }
        return NSPoint(
            x: cocoa.x - frame.origin.x,
            y: frame.origin.y + frame.size.height - cocoa.y
        )
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)

        NSColor.black.withAlphaComponent(0.35).setFill()
        bounds.fill()

        let state = SelectionState.shared
        let c1Local = state.corner1Quartz.flatMap { quartzToLocal($0) }
        let cur = cursorLocal

        if let c1 = c1Local, let cur = cur {
            let rect = NSRect(
                x: min(c1.x, cur.x),
                y: min(c1.y, cur.y),
                width: abs(cur.x - c1.x),
                height: abs(cur.y - c1.y)
            )
            NSColor.black.withAlphaComponent(0.05).setFill()
            rect.fill()

            NSColor(calibratedRed: 0.3, green: 0.75, blue: 1.0, alpha: 0.95).setStroke()
            let path = NSBezierPath(rect: rect)
            path.lineWidth = 2
            path.stroke()
            drawHandle(at: c1)
            drawHandle(at: cur)
        } else if let c1 = c1Local {
            drawHandle(at: c1)
        } else if let q1 = state.corner1Quartz, let cur = cur {
            // First corner is on another display — still show rubber-band from edge
            // Just show cursor handle
            drawHandle(at: cur)
            _ = q1
        }

        if let cur = cur {
            NSColor.white.withAlphaComponent(0.55).setStroke()
            let cross = NSBezierPath()
            cross.lineWidth = 1
            cross.move(to: NSPoint(x: 0, y: cur.y))
            cross.line(to: NSPoint(x: bounds.width, y: cur.y))
            cross.move(to: NSPoint(x: cur.x, y: 0))
            cross.line(to: NSPoint(x: cur.x, y: bounds.height))
            cross.stroke()
        }

        drawBanner(state.instruction)
    }

    private func drawHandle(at p: NSPoint) {
        let s: CGFloat = 8
        let r = NSRect(x: p.x - s/2, y: p.y - s/2, width: s, height: s)
        NSColor(calibratedRed: 0.3, green: 0.75, blue: 1.0, alpha: 1.0).setFill()
        NSBezierPath(ovalIn: r).fill()
    }

    private func drawBanner(_ instruction: String) {
        let attrs: [NSAttributedString.Key: Any] = [
            .font: NSFont.boldSystemFont(ofSize: 16),
            .foregroundColor: NSColor.white
        ]
        let text = instruction as NSString
        let size = text.size(withAttributes: attrs)
        let padX: CGFloat = 20
        let padY: CGFloat = 12
        let bw = size.width + padX * 2
        let bh = size.height + padY * 2
        let bx = (bounds.width - bw) / 2
        let by: CGFloat = 48
        let banner = NSRect(x: bx, y: by, width: bw, height: bh)

        NSColor.black.withAlphaComponent(0.75).setFill()
        NSBezierPath(roundedRect: banner, xRadius: 10, yRadius: 10).fill()
        text.draw(at: NSPoint(x: bx + padX, y: by + padY), withAttributes: attrs)
    }

    override func mouseMoved(with event: NSEvent) {
        cursorLocal = convert(event.locationInWindow, from: nil)
        needsDisplay = true
    }

    override func mouseDragged(with event: NSEvent) {
        mouseMoved(with: event)
    }

    override func mouseDown(with event: NSEvent) {
        let local = convert(event.locationInWindow, from: nil)
        cursorLocal = local
        let q = localToQuartz(local)
        let state = SelectionState.shared

        if state.corner1Quartz == nil {
            state.corner1Quartz = q
            state.instruction = "Click opposite corner  ·  Esc to cancel"
            state.delegate?.refreshAll()
        } else {
            state.delegate?.finish(p1: state.corner1Quartz!, p2: q)
        }
    }

    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 {
            SelectionState.shared.delegate?.cancel()
        }
    }

    override func resetCursorRects() {
        addCursorRect(bounds, cursor: .crosshair)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var windows: [NSWindow] = []
    private var views: [OverlayView] = []
    private var finished = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        SelectionState.shared.delegate = self
        NSApp.setActivationPolicy(.accessory)
        NSCursor.crosshair.set()

        for screen in NSScreen.screens {
            let win = NSWindow(
                contentRect: screen.frame,
                styleMask: .borderless,
                backing: .buffered,
                defer: false,
                screen: screen
            )
            win.isOpaque = false
            win.backgroundColor = .clear
            win.level = .screenSaver
            win.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
            win.ignoresMouseEvents = false
            win.acceptsMouseMovedEvents = true
            win.setFrame(screen.frame, display: true)

            let view = OverlayView(frame: win.contentView!.bounds, screen: screen)
            view.autoresizingMask = [.width, .height]

            win.contentView = view
            win.makeKeyAndOrderFront(nil)

            windows.append(win)
            views.append(view)
        }

        // Key window = main screen overlay so Esc works
        if let first = windows.first {
            first.makeKeyAndOrderFront(nil)
            first.makeFirstResponder(first.contentView)
        }

        NSApp.activate(ignoringOtherApps: true)

        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            if event.keyCode == 53 {
                self?.cancel()
                return nil
            }
            return event
        }

        // Track mouse across displays even when another overlay is key
        NSEvent.addLocalMonitorForEvents(matching: [.mouseMoved, .leftMouseDragged]) { event in
            // Forward to the view under the cursor
            if let screen = NSScreen.screens.first(where: { NSMouseInRect(NSEvent.mouseLocation, $0.frame, false) }),
               let pair = self.windows.enumerated().first(where: { $0.element.screen == screen }) {
                let view = self.views[pair.offset]
                let win = pair.element
                let locInWin = win.mouseLocationOutsideOfEventStream
                view.cursorLocal = view.convert(locInWin, from: nil)
                view.needsDisplay = true
            }
            return event
        }
    }

    func refreshAll() {
        for v in views { v.needsDisplay = true }
    }

    func finish(p1: CGPoint, p2: CGPoint) {
        guard !finished else { return }
        finished = true

        var x = min(p1.x, p2.x)
        var y = min(p1.y, p2.y)
        var w = abs(p2.x - p1.x)
        var h = abs(p2.y - p1.y)
        if w < 1 { w = 1 }
        if h < 1 { h = 1 }

        teardown()
        print("\(Int(round(x))),\(Int(round(y))),\(Int(round(w))),\(Int(round(h)))")
        fflush(stdout)
        NSApp.terminate(nil)
    }

    func cancel() {
        guard !finished else { return }
        finished = true
        teardown()
        fputs("cancelled\n", stderr)
        exit(1)
    }

    private func teardown() {
        for w in windows { w.orderOut(nil) }
        windows.removeAll()
        views.removeAll()
        NSCursor.arrow.set()
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
