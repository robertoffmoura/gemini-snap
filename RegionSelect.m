/*
 * Two-click region selector for macOS (Objective-C — no Swift).
 * Prints: x,y,w,h  (Quartz / screencapture -R, top-left origin)
 * Exit 0 success, 1 cancel.
 *
 * Build:
 *   clang -fobjc-arc -framework Cocoa -o region_select RegionSelect.m
 */

#import <Cocoa/Cocoa.h>

// Shared across all displays
static BOOL gHasCorner1 = NO;
static CGPoint gCorner1Quartz; // top-left origin
static NSString *gInstruction = nil;
static id gDelegate = nil;

static CGFloat GSMaxScreenY(void) {
  NSArray<NSScreen *> *screens = [NSScreen screens];
  if (screens.count > 0) {
    return NSMaxY(screens[0].frame);
  }
  return 0;
}

static CGPoint GSLocalToQuartz(NSPoint local, NSScreen *screen) {
  NSRect frame = screen.frame;
  // flipped local y = distance from top of this screen
  NSPoint cocoa = NSMakePoint(frame.origin.x + local.x,
                              frame.origin.y + frame.size.height - local.y);
  CGFloat maxY = GSMaxScreenY();
  return CGPointMake(cocoa.x, maxY - cocoa.y);
}

static BOOL GSQuartzToLocal(CGPoint q, NSScreen *screen, NSPoint *outLocal) {
  NSRect frame = screen.frame;
  CGFloat maxY = GSMaxScreenY();
  NSPoint cocoa = NSMakePoint(q.x, maxY - q.y);
  if (cocoa.x < NSMinX(frame) || cocoa.x > NSMaxX(frame) ||
      cocoa.y < NSMinY(frame) || cocoa.y > NSMaxY(frame)) {
    return NO;
  }
  *outLocal = NSMakePoint(cocoa.x - frame.origin.x,
                          frame.origin.y + frame.size.height - cocoa.y);
  return YES;
}

@interface GSOverlayView : NSView
@property(nonatomic, assign) NSPoint cursor;
@property(nonatomic, weak) NSScreen *ownScreen;
@end

@interface GSAppDelegate : NSObject <NSApplicationDelegate>
- (void)finishWithP2Quartz:(CGPoint)p2;
- (void)cancel;
- (void)refreshAll;
@end

@implementation GSOverlayView

- (BOOL)isFlipped {
  return YES;
}
- (BOOL)acceptsFirstResponder {
  return YES;
}

- (void)drawRect:(NSRect)dirty {
  [[NSColor colorWithCalibratedWhite:0 alpha:0.35] setFill];
  NSRectFill(self.bounds);

  NSPoint c1Local;
  BOOL c1Here =
      gHasCorner1 && GSQuartzToLocal(gCorner1Quartz, self.ownScreen, &c1Local);
  NSPoint cur = self.cursor;

  if (c1Here) {
    NSRect sel = NSMakeRect(MIN(c1Local.x, cur.x), MIN(c1Local.y, cur.y),
                            fabs(cur.x - c1Local.x), fabs(cur.y - c1Local.y));
    [[NSColor colorWithCalibratedWhite:0 alpha:0.05] setFill];
    NSRectFill(sel);

    [[NSColor colorWithCalibratedRed:0.3 green:0.75 blue:1 alpha:0.95] setStroke];
    NSBezierPath *p = [NSBezierPath bezierPathWithRect:sel];
    p.lineWidth = 2.0;
    [p stroke];
    [self drawHandle:c1Local];
    [self drawHandle:cur];
  } else if (gHasCorner1) {
    // First corner on another display — still show cursor handle
    [self drawHandle:cur];
  }

  [[NSColor colorWithCalibratedWhite:1 alpha:0.55] setStroke];
  NSBezierPath *cross = [NSBezierPath bezierPath];
  cross.lineWidth = 1.0;
  [cross moveToPoint:NSMakePoint(0, cur.y)];
  [cross lineToPoint:NSMakePoint(NSWidth(self.bounds), cur.y)];
  [cross moveToPoint:NSMakePoint(cur.x, 0)];
  [cross lineToPoint:NSMakePoint(cur.x, NSHeight(self.bounds))];
  [cross stroke];

  [self drawBanner];
}

- (void)drawHandle:(NSPoint)pt {
  CGFloat s = 8;
  NSRect r = NSMakeRect(pt.x - s / 2, pt.y - s / 2, s, s);
  [[NSColor colorWithCalibratedRed:0.3 green:0.75 blue:1 alpha:1] setFill];
  [[NSBezierPath bezierPathWithOvalInRect:r] fill];
}

- (void)drawBanner {
  NSDictionary *attrs = @{
    NSFontAttributeName : [NSFont boldSystemFontOfSize:16],
    NSForegroundColorAttributeName : [NSColor whiteColor]
  };
  NSString *text = gInstruction ?: @"Click first corner  ·  Esc to cancel";
  NSSize size = [text sizeWithAttributes:attrs];
  CGFloat padX = 20, padY = 12;
  CGFloat bw = size.width + padX * 2;
  CGFloat bh = size.height + padY * 2;
  CGFloat bx = (NSWidth(self.bounds) - bw) / 2;
  CGFloat by = 48;
  NSRect banner = NSMakeRect(bx, by, bw, bh);
  [[NSColor colorWithCalibratedWhite:0.05 alpha:0.8] setFill];
  [[NSBezierPath bezierPathWithRoundedRect:banner xRadius:10 yRadius:10] fill];
  [text drawAtPoint:NSMakePoint(bx + padX, by + padY) withAttributes:attrs];
}

- (void)mouseMoved:(NSEvent *)event {
  self.cursor = [self convertPoint:event.locationInWindow fromView:nil];
  [self setNeedsDisplay:YES];
}

- (void)mouseDragged:(NSEvent *)event {
  [self mouseMoved:event];
}

- (void)mouseDown:(NSEvent *)event {
  NSPoint local = [self convertPoint:event.locationInWindow fromView:nil];
  self.cursor = local;
  CGPoint q = GSLocalToQuartz(local, self.ownScreen);

  if (!gHasCorner1) {
    gCorner1Quartz = q;
    gHasCorner1 = YES;
    gInstruction = @"Click opposite corner  ·  Esc to cancel";
    [(GSAppDelegate *)gDelegate refreshAll];
  } else {
    [(GSAppDelegate *)gDelegate finishWithP2Quartz:q];
  }
}

- (void)keyDown:(NSEvent *)event {
  if (event.keyCode == 53) {
    [(GSAppDelegate *)gDelegate cancel];
  }
}

- (void)resetCursorRects {
  [self addCursorRect:self.bounds cursor:[NSCursor crosshairCursor]];
}

@end

@implementation GSAppDelegate {
  NSMutableArray<NSWindow *> *_windows;
  NSMutableArray<GSOverlayView *> *_views;
  BOOL _finished;
}

- (void)applicationDidFinishLaunching:(NSNotification *)note {
  _windows = [NSMutableArray array];
  _views = [NSMutableArray array];
  _finished = NO;
  gDelegate = self;
  gHasCorner1 = NO;
  gInstruction = @"Click first corner  ·  Esc to cancel";

  [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
  [[NSCursor crosshairCursor] set];

  for (NSScreen *screen in [NSScreen screens]) {
    NSWindow *win = [[NSWindow alloc]
        initWithContentRect:screen.frame
                  styleMask:NSWindowStyleMaskBorderless
                    backing:NSBackingStoreBuffered
                      defer:NO
                     screen:screen];
    win.opaque = NO;
    win.backgroundColor = [NSColor clearColor];
    win.level = NSScreenSaverWindowLevel;
    win.collectionBehavior = NSWindowCollectionBehaviorCanJoinAllSpaces |
                             NSWindowCollectionBehaviorFullScreenAuxiliary |
                             NSWindowCollectionBehaviorIgnoresCycle;
    win.ignoresMouseEvents = NO;
    win.acceptsMouseMovedEvents = YES;
    [win setFrame:screen.frame display:YES];

    GSOverlayView *view =
        [[GSOverlayView alloc] initWithFrame:win.contentView.bounds];
    view.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    view.ownScreen = screen;
    view.cursor = NSMakePoint(NSWidth(view.bounds) / 2, NSHeight(view.bounds) / 2);

    win.contentView = view;
    [win makeKeyAndOrderFront:nil];
    [_windows addObject:win];
    [_views addObject:view];
  }

  if (_windows.count) {
    [_windows[0] makeKeyAndOrderFront:nil];
    [_windows[0] makeFirstResponder:_windows[0].contentView];
  }

  [NSApp activateIgnoringOtherApps:YES];

  [NSEvent addLocalMonitorForEventsMatchingMask:NSEventMaskKeyDown
                                        handler:^NSEvent *(NSEvent *e) {
                                          if (e.keyCode == 53) {
                                            [self cancel];
                                            return nil;
                                          }
                                          return e;
                                        }];
}

- (void)refreshAll {
  for (GSOverlayView *v in _views)
    [v setNeedsDisplay:YES];
}

- (void)finishWithP2Quartz:(CGPoint)p2 {
  if (_finished)
    return;
  _finished = YES;

  CGFloat x = MIN(gCorner1Quartz.x, p2.x);
  CGFloat y = MIN(gCorner1Quartz.y, p2.y);
  CGFloat w = fabs(p2.x - gCorner1Quartz.x);
  CGFloat h = fabs(p2.y - gCorner1Quartz.y);
  if (w < 1)
    w = 1;
  if (h < 1)
    h = 1;

  [self teardown];
  printf("%d,%d,%d,%d\n", (int)lround(x), (int)lround(y), (int)lround(w),
         (int)lround(h));
  fflush(stdout);
  [NSApp terminate:nil];
}

- (void)cancel {
  if (_finished)
    return;
  _finished = YES;
  [self teardown];
  fprintf(stderr, "cancelled\n");
  exit(1);
}

- (void)teardown {
  for (NSWindow *w in _windows)
    [w orderOut:nil];
  [_windows removeAllObjects];
  [_views removeAllObjects];
  [[NSCursor arrowCursor] set];
}

@end

int main(int argc, const char *argv[]) {
  @autoreleasepool {
    NSApplication *app = [NSApplication sharedApplication];
    GSAppDelegate *delegate = [GSAppDelegate new];
    app.delegate = delegate;
    [app run];
  }
  return 0;
}
