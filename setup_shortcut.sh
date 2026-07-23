#!/bin/zsh
# setup_shortcut.sh
# Programmatically creates a macOS Quick Action (Service) and registers its keyboard shortcut (⌥⌘G)
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script only runs on macOS." >&2
  exit 1
fi

# 1. Determine absolute path of run.sh
ROOT="$(cd "$(dirname "$0")" && pwd)"
RUN_SH="$ROOT/run.sh"

if [[ ! -f "$RUN_SH" ]]; then
  echo "Error: run.sh not found in $ROOT" >&2
  exit 1
fi

SERVICE_NAME="Gemini Snap"
WORKFLOW_DIR="$HOME/Library/Services/${SERVICE_NAME}.workflow"
CONTENTS_DIR="$WORKFLOW_DIR/Contents"

echo "==> Creating macOS Quick Action bundle..."
mkdir -p "$CONTENTS_DIR"

# 2. Write Info.plist
cat <<EOF > "$CONTENTS_DIR/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key>
	<string>English</string>
	<key>CFBundleGetInfoString</key>
	<string>${SERVICE_NAME}</string>
	<key>CFBundleIdentifier</key>
	<string>com.apple.Automator.GeminiSnap</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundleName</key>
	<string>${SERVICE_NAME}</string>
	<key>CFBundlePackageType</key>
	<string>BNDL</string>
	<key>CFBundleShortVersionString</key>
	<string>1.0</string>
	<key>CFBundleSignature</key>
	<string>????</string>
	<key>CFBundleVersion</key>
	<string>1.0</string>
	<key>NSPrincipalClass</key>
	<string>AMWorkflowController</string>
</dict>
</plist>
EOF

# 3. Write document.wflow XML (runs run.sh in the background)
cat <<EOF > "$CONTENTS_DIR/document.wflow"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>actions</key>
	<array>
		<dict>
			<key>action</key>
			<dict>
				<key>ActionBundlePath</key>
				<string>/System/Library/Automator/Run Shell Script.action</string>
				<key>ActionName</key>
				<string>Run Shell Script</string>
				<key>ActionParameters</key>
				<dict>
					<key>COMMAND_STRING</key>
					<string>/bin/zsh "${RUN_SH}"</string>
					<key>CheckedForUserDefaultShell</key>
					<true/>
					<key>inputMethod</key>
					<integer>0</integer>
					<key>shell</key>
					<string>/bin/zsh</string>
					<key>source</key>
					<string></string>
				</dict>
				<key>BundleIdentifier</key>
				<string>com.apple.RunShellScript</string>
				<key>CFBundleVersion</key>
				<string>2.0.3</string>
				<key>CanShowSelectedItemsWhenRun</key>
				<false/>
				<key>CanShowWhenRun</key>
				<true/>
				<key>Category</key>
				<array>
					<string>AMCategoryUtilities</string>
				</array>
				<key>Class Name</key>
				<string>RunShellScriptAction</string>
				<key>InputUUID</key>
				<string>B62BBA69-4252-441F-B7F9-AF6676A1B29E</string>
				<key>Keywords</key>
				<array>
					<string>Shell</string>
					<string>Script</string>
					<string>Command</string>
					<string>Run</string>
				</array>
				<key>OutputUUID</key>
				<string>63C42587-AA25-46D1-9B56-5B8AC939CC94</string>
				<key>UUID</key>
				<string>33C1488B-D409-4C5C-BDC3-C5EE9EFD00FF</string>
				<key>UnlocalizedApplications</key>
				<array>
					<string>Automator</string>
				</array>
				<key>arguments</key>
				<dict>
					<key>0</key>
					<dict>
						<key>default value</key>
						<integer>0</integer>
						<key>name</key>
						<string>inputMethod</string>
						<key>type</key>
						<string>0</string>
					</dict>
					<key>1</key>
					<dict>
						<key>default value</key>
						<false/>
						<key>name</key>
						<string>CheckedForUserDefaultShell</string>
						<key>type</key>
						<string>0</string>
					</dict>
					<key>2</key>
					<dict>
						<key>default value</key>
						<string></string>
						<key>name</key>
						<string>source</string>
						<key>type</key>
						<string>0</string>
					</dict>
					<key>3</key>
					<dict>
						<key>default value</key>
						<string></string>
						<key>name</key>
						<string>COMMAND_STRING</string>
						<key>type</key>
						<string>0</string>
					</dict>
					<key>4</key>
					<dict>
						<key>default value</key>
						<string>/bin/sh</string>
						<key>name</key>
						<string>shell</string>
						<key>type</key>
						<string>0</string>
					</dict>
				</dict>
				<key>isViewVisible</key>
				<integer>1</integer>
				<key>location</key>
				<string>309.000000:305.000000</string>
				<key>nibName</key>
				<string>RunShellScriptAction</string>
			</dict>
			<key>isViewVisible</key>
			<integer>1</integer>
		</dict>
	</array>
	<key>connectors</key>
	<dict/>
	<key>workflowMetaData</key>
	<dict>
		<key>inputTypeIdentifier</key>
		<string>com.apple.Automator.nothing</string>
		<key>outputTypeIdentifier</key>
		<string>com.apple.Automator.nothing</string>
		<key>presentationMode</key>
		<integer>11</integer>
		<key>showInInputItems</key>
		<integer>0</integer>
		<key>showInShareMenu</key>
		<false/>
		<key>stages</key>
		<array/>
		<key>toSystemWideDefaults</key>
		<true/>
	</dict>
</dict>
</plist>
EOF

chmod +x "$RUN_SH"

# 4. Register keyboard shortcut in pbs.plist
echo "==> Registering keyboard shortcut (⌥⌘G)..."
PLIST="$HOME/Library/Preferences/pbs.plist"
KEY_PATH=":NSServicesStatus:'(null) - ${SERVICE_NAME} - runWorkflowAsService':key_equivalent"

# Make sure plist exists/is valid XML or binary
if [[ ! -f "$PLIST" ]]; then
  echo '<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict></dict></plist>' > "$PLIST"
fi

# Add or set key_equivalent to ~@g (Option + Command + G)
/usr/libexec/PlistBuddy -c "Add ${KEY_PATH} string '~@g'" "$PLIST" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Set ${KEY_PATH} '~@g'" "$PLIST"

# 5. Force update the macOS services cache
echo "==> Force updating macOS services cache..."
/System/Library/CoreServices/pbs -update

echo "==> Done! Try pressing ⌥⌘G (Option + Command + G) to capture."
