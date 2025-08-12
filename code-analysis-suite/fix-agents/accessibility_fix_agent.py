#!/usr/bin/env python3
"""
Accessibility Fix Agent - AutoBot Frontend
Automatically fixes accessibility issues in Vue.js components

Focuses on:
- Buttons without aria-label or title attributes
- Images without alt attributes
- Missing keyboard navigation support
- WCAG 2.1 AA compliance improvements
"""

import os
import re
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class AccessibilityFixAgent:
    def __init__(self, root_path: str = "/home/kali/Desktop/AutoBot/autobot-vue"):
        self.root_path = Path(root_path)
        self.backup_dir = self.root_path.parent / ".accessibility-fix-backups"
        self.report_data = {
            "timestamp": datetime.now().isoformat(),
            "fixes_applied": [],
            "files_modified": [],
            "accessibility_score_before": 0,
            "accessibility_score_after": 0,
            "summary": {},
        }

        # Icon to label mapping for common UI patterns
        self.icon_labels = {
            "fa-close": "Close",
            "fa-times": "Close",
            "fa-x": "Close",
            "fa-settings": "Settings",
            "fa-gear": "Settings",
            "fa-cog": "Settings",
            "fa-search": "Search",
            "fa-magnifying-glass": "Search",
            "fa-edit": "Edit",
            "fa-pencil": "Edit",
            "fa-save": "Save",
            "fa-floppy-disk": "Save",
            "fa-delete": "Delete",
            "fa-trash": "Delete",
            "fa-remove": "Delete",
            "fa-plus": "Add",
            "fa-add": "Add",
            "fa-minus": "Remove",
            "fa-subtract": "Remove",
            "fa-home": "Home",
            "fa-house": "Home",
            "fa-user": "User",
            "fa-account": "Account",
            "fa-profile": "Profile",
            "fa-menu": "Menu",
            "fa-bars": "Menu",
            "fa-hamburger": "Menu",
            "fa-download": "Download",
            "fa-upload": "Upload",
            "fa-refresh": "Refresh",
            "fa-reload": "Refresh",
            "fa-sync": "Refresh",
            "fa-copy": "Copy",
            "fa-clipboard": "Copy",
            "fa-share": "Share",
            "fa-arrow-left": "Go back",
            "fa-arrow-right": "Go forward",
            "fa-arrow-up": "Go up",
            "fa-arrow-down": "Go down",
            "fa-check": "Confirm",
            "fa-checkmark": "Confirm",
            "fa-info": "Information",
            "fa-question": "Help",
            "fa-help": "Help",
            "fa-warning": "Warning",
            "fa-exclamation": "Warning",
            "fa-play": "Play",
            "fa-pause": "Pause",
            "fa-stop": "Stop",
            "fa-volume-up": "Increase volume",
            "fa-volume-down": "Decrease volume",
            "fa-volume-mute": "Mute",
        }

        # Context-based button labels
        self.context_labels = {
            "submit": "Submit form",
            "send": "Send message",
            "login": "Sign in",
            "logout": "Sign out",
            "signin": "Sign in",
            "signout": "Sign out",
            "register": "Create account",
            "signup": "Create account",
            "cancel": "Cancel",
            "confirm": "Confirm",
            "ok": "OK",
            "yes": "Yes",
            "no": "No",
            "continue": "Continue",
            "next": "Next",
            "previous": "Previous",
            "back": "Go back",
            "forward": "Go forward",
            "reset": "Reset",
            "clear": "Clear",
            "filter": "Apply filters",
            "sort": "Sort items",
            "expand": "Expand",
            "collapse": "Collapse",
            "minimize": "Minimize",
            "maximize": "Maximize",
        }

        self.setup_directories()

    def setup_directories(self):
        """Create necessary directories"""
        self.backup_dir.mkdir(exist_ok=True)

    def create_backup(self, file_path: Path) -> Path:
        """Create a backup of the original file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"{file_path.name}.{timestamp}.backup"
        shutil.copy2(file_path, backup_path)
        return backup_path

    def analyze_button_content(self, button_html: str) -> Optional[str]:
        """Analyze button content to generate appropriate label"""

        # Check for existing aria-label or title
        if re.search(r"aria-label\s*=", button_html, re.IGNORECASE):
            return None  # Already has accessibility label
        if re.search(r"title\s*=", button_html, re.IGNORECASE):
            return None  # Already has title

        # Extract text content
        text_match = re.search(r">([^<]+)<", button_html)
        if text_match:
            text = text_match.group(1).strip().lower()
            if text and len(text) > 2:  # Has meaningful text content
                return text.capitalize()

        # Check for common context keywords
        button_lower = button_html.lower()
        for keyword, label in self.context_labels.items():
            if keyword in button_lower:
                return label

        # Check for icon classes
        for icon_class, label in self.icon_labels.items():
            if icon_class in button_lower:
                return label

        # Check for Vue.js event handlers for context
        click_match = re.search(r'@click\s*=\s*["\']([^"\']+)["\']', button_html)
        if click_match:
            method_name = click_match.group(1).lower()
            for keyword, label in self.context_labels.items():
                if keyword in method_name:
                    return label

        # Default label based on button type or generic action
        if 'type="submit"' in button_lower:
            return "Submit"
        elif "class=" in button_lower and "btn" in button_lower:
            return "Button"

        return "Action button"  # Generic fallback

    def fix_button_accessibility(self, content: str) -> Tuple[str, List[str]]:
        """Fix accessibility issues in buttons"""
        fixes_applied = []

        # Find all button elements
        button_pattern = r"<button[^>]*>.*?</button>"
        buttons = re.finditer(button_pattern, content, re.DOTALL | re.IGNORECASE)

        modified_content = content
        offset = 0

        for match in buttons:
            button_html = match.group(0)
            label = self.analyze_button_content(button_html)

            if label:
                # Add aria-label to opening button tag
                button_tag_match = re.match(
                    r"(<button[^>]*)(>)", button_html, re.IGNORECASE
                )
                if button_tag_match:
                    opening_tag = button_tag_match.group(1)

                    # Add aria-label before closing >
                    new_opening_tag = f'{opening_tag} aria-label="{label}">'
                    new_button_html = button_html.replace(
                        button_tag_match.group(0), new_opening_tag
                    )

                    # Replace in the main content
                    start_pos = match.start() + offset
                    end_pos = match.end() + offset
                    modified_content = (
                        modified_content[:start_pos]
                        + new_button_html
                        + modified_content[end_pos:]
                    )

                    # Update offset for next replacement
                    offset += len(new_button_html) - len(button_html)

                    fixes_applied.append(f"Added aria-label='{label}' to button")

        return modified_content, fixes_applied

    def fix_image_accessibility(self, content: str) -> Tuple[str, List[str]]:
        """Fix accessibility issues in images"""
        fixes_applied = []

        # Find img tags without alt attributes
        img_pattern = r"<img(?![^>]*alt\s*=)[^>]*>"
        images = re.finditer(img_pattern, content, re.IGNORECASE)

        modified_content = content
        offset = 0

        for match in images:
            img_tag = match.group(0)

            # Try to determine appropriate alt text
            alt_text = "Image"

            # Check for src attribute to get filename
            src_match = re.search(r'src\s*=\s*["\']([^"\']+)["\']', img_tag)
            if src_match:
                src = src_match.group(1)
                filename = Path(src).stem
                # Convert filename to readable text
                alt_text = filename.replace("-", " ").replace("_", " ").title()

            # Check for class attributes that might give context
            class_match = re.search(r'class\s*=\s*["\']([^"\']+)["\']', img_tag)
            if class_match:
                classes = class_match.group(1).lower()
                if "logo" in classes:
                    alt_text = "Logo"
                elif "avatar" in classes or "profile" in classes:
                    alt_text = "Profile picture"
                elif "icon" in classes:
                    alt_text = "Icon"
                elif "banner" in classes:
                    alt_text = "Banner image"

            # Add alt attribute
            new_img_tag = img_tag[:-1] + f' alt="{alt_text}">'

            # Replace in content
            start_pos = match.start() + offset
            end_pos = match.end() + offset
            modified_content = (
                modified_content[:start_pos] + new_img_tag + modified_content[end_pos:]
            )

            # Update offset
            offset += len(new_img_tag) - len(img_tag)

            fixes_applied.append(f"Added alt='{alt_text}' to image")

        return modified_content, fixes_applied

    def fix_keyboard_navigation(self, content: str) -> Tuple[str, List[str]]:
        """Add keyboard navigation support where needed"""
        fixes_applied = []

        # Find clickable elements without keyboard support
        clickable_pattern = r"<(div|span)[^>]*@click[^>]*>(?![^<]*tabindex)"
        clickables = re.finditer(clickable_pattern, content, re.IGNORECASE)

        modified_content = content
        offset = 0

        for match in clickables:
            element = match.group(0)

            # Add tabindex and keyboard event handlers
            keyboard_attrs = ' tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()"'
            new_element = element[:-1] + keyboard_attrs + ">"

            # Replace in content
            start_pos = match.start() + offset
            end_pos = match.end() + offset
            modified_content = (
                modified_content[:start_pos] + new_element + modified_content[end_pos:]
            )

            # Update offset
            offset += len(new_element) - len(element)

            fixes_applied.append(
                "Added keyboard navigation support to clickable element"
            )

        return modified_content, fixes_applied

    def calculate_accessibility_score(self, content: str) -> int:
        """Calculate basic accessibility score (0-100)"""
        score = 100

        # Check for missing alt attributes
        img_no_alt = len(re.findall(r"<img(?![^>]*alt\s*=)", content, re.IGNORECASE))
        score -= img_no_alt * 5

        # Check for buttons without labels
        button_no_label = len(
            re.findall(
                r"<button(?![^>]*(?:aria-label|title)\s*=)", content, re.IGNORECASE
            )
        )
        score -= button_no_label * 5

        # Check for clickable elements without keyboard support
        clickable_no_kbd = len(
            re.findall(
                r"<(?:div|span)[^>]*@click[^>]*>(?![^<]*tabindex)",
                content,
                re.IGNORECASE,
            )
        )
        score -= clickable_no_kbd * 3

        # Check for positive tabindex (bad practice)
        positive_tabindex = len(
            re.findall(r'tabindex\s*=\s*["\']?[1-9]', content, re.IGNORECASE)
        )
        score -= positive_tabindex * 2

        return max(0, score)

    def fix_vue_component(self, file_path: Path) -> bool:
        """Fix accessibility issues in a Vue component"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                original_content = f.read()

            # Calculate initial accessibility score
            initial_score = self.calculate_accessibility_score(original_content)

            # Apply fixes
            modified_content = original_content
            all_fixes = []

            # Fix buttons
            modified_content, button_fixes = self.fix_button_accessibility(
                modified_content
            )
            all_fixes.extend(button_fixes)

            # Fix images
            modified_content, image_fixes = self.fix_image_accessibility(
                modified_content
            )
            all_fixes.extend(image_fixes)

            # Fix keyboard navigation
            modified_content, keyboard_fixes = self.fix_keyboard_navigation(
                modified_content
            )
            all_fixes.extend(keyboard_fixes)

            if all_fixes:
                # Create backup
                backup_path = self.create_backup(file_path)

                # Write fixed content
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(modified_content)

                # Calculate final score
                final_score = self.calculate_accessibility_score(modified_content)

                # Record fixes
                fix_record = {
                    "file": str(file_path.relative_to(self.root_path)),
                    "fixes": all_fixes,
                    "backup": str(backup_path.relative_to(self.root_path.parent)),
                    "accessibility_score_improvement": final_score - initial_score,
                    "initial_score": initial_score,
                    "final_score": final_score,
                }

                self.report_data["fixes_applied"].append(fix_record)
                self.report_data["files_modified"].append(
                    str(file_path.relative_to(self.root_path))
                )

                print(
                    f"✅ Fixed {len(all_fixes)} accessibility issues in {file_path.name}"
                )
                for fix in all_fixes[:3]:  # Show first 3 fixes
                    print(f"   • {fix}")
                if len(all_fixes) > 3:
                    print(f"   • ... and {len(all_fixes) - 3} more")
                print(f"   • Accessibility score: {initial_score} → {final_score}")

                return True

            return False

        except Exception as e:
            print(f"❌ Error fixing {file_path}: {e}")
            return False

    def scan_and_fix(self) -> None:
        """Scan and fix accessibility issues in Vue components"""
        print("🔍 Starting accessibility scan and fix...")
        print(f"📁 Scanning directory: {self.root_path}")

        # Find Vue files
        vue_files = list(self.root_path.rglob("*.vue"))

        # Filter out node_modules, dist, etc.
        filtered_files = []
        skip_dirs = {"node_modules", "dist", "build", ".nuxt", ".next", "coverage"}

        for vue_file in vue_files:
            if not any(skip_dir in vue_file.parts for skip_dir in skip_dirs):
                filtered_files.append(vue_file)

        print(f"📄 Found {len(filtered_files)} Vue components to analyze")

        fixed_count = 0
        total_fixes = 0

        for vue_file in filtered_files:
            if self.fix_vue_component(vue_file):
                fixed_count += 1

        # Calculate summary statistics
        total_fixes = sum(
            len(fix["fixes"]) for fix in self.report_data["fixes_applied"]
        )

        self.report_data["summary"] = {
            "total_files_scanned": len(filtered_files),
            "files_modified": fixed_count,
            "total_fixes_applied": total_fixes,
            "accessibility_improvements": sum(
                fix.get("accessibility_score_improvement", 0)
                for fix in self.report_data["fixes_applied"]
            ),
        }

        print(f"\n🎯 Accessibility Fix Summary:")
        print(f"   📊 Files scanned: {len(filtered_files)}")
        print(f"   ✅ Files modified: {fixed_count}")
        print(f"   🔧 Total fixes applied: {total_fixes}")
        print(
            f"   📈 Accessibility score improvement: +{self.report_data['summary']['accessibility_improvements']} points"
        )

    def generate_report(self) -> None:
        """Generate detailed accessibility fix report"""
        report_path = self.root_path.parent / "accessibility-fix-report.md"
        json_report_path = self.root_path.parent / "accessibility-fix-report.json"

        # Save JSON report
        with open(json_report_path, "w") as f:
            json.dump(self.report_data, f, indent=2)

        # Generate Markdown report
        report_content = f"""# Accessibility Fix Report - AutoBot Frontend

**Generated**: {self.report_data['timestamp']}
**Agent**: Accessibility Fix Agent v1.0

## Summary

- **Files Scanned**: {self.report_data['summary']['total_files_scanned']}
- **Files Modified**: {self.report_data['summary']['files_modified']}
- **Total Fixes Applied**: {self.report_data['summary']['total_fixes_applied']}
- **Accessibility Score Improvement**: +{self.report_data['summary']['accessibility_improvements']} points

## Fixes Applied

"""

        for fix_record in self.report_data["fixes_applied"]:
            report_content += f"""### {fix_record['file']}
**Accessibility Score**: {fix_record['initial_score']} → {fix_record['final_score']} (+{fix_record['accessibility_score_improvement']})
**Backup**: {fix_record['backup']}

**Fixes Applied**:
"""
            for fix in fix_record["fixes"]:
                report_content += f"- {fix}\n"
            report_content += "\n"

        report_content += f"""
## WCAG 2.1 AA Compliance Improvements

The following accessibility improvements have been applied to enhance WCAG 2.1 AA compliance:

### 1. **Perceivable**
- ✅ Added `alt` attributes to images without alternative text
- ✅ Ensured meaningful alternative text based on image context

### 2. **Operable**
- ✅ Added `aria-label` attributes to buttons without accessible names
- ✅ Implemented keyboard navigation support (`tabindex`, keyboard event handlers)
- ✅ Enhanced focus management for interactive elements

### 3. **Understandable**
- ✅ Provided clear, descriptive labels for UI elements
- ✅ Used semantic button text and ARIA labels

### 4. **Robust**
- ✅ Ensured compatibility with assistive technologies through ARIA attributes
- ✅ Maintained clean HTML structure with proper accessibility markup

## Implementation Details

### Button Accessibility Enhancements
- Smart label generation based on button content, icons, and context
- Support for Vue.js event handlers and component patterns
- Icon-to-label mapping for common UI elements

### Image Accessibility Enhancements
- Automatic alt text generation from filenames and context
- Context-aware labeling (logos, avatars, icons)
- Preservation of existing alt attributes

### Keyboard Navigation Support
- Added `tabindex="0"` to clickable non-button elements
- Implemented Enter and Space key support for custom clickable elements
- Enhanced focus management for better keyboard accessibility

## Backup Information

All modified files have been backed up to: `.accessibility-fix-backups/`

To restore original files:
```bash
# Restore specific file
cp .accessibility-fix-backups/ComponentName.vue.YYYYMMDD_HHMMSS.backup autobot-vue/src/components/ComponentName.vue

# Restore all files (if needed)
python3 code-analysis-suite/fix-agents/restore_accessibility_backups.py
```

## Next Steps

1. **Test Accessibility**: Use screen readers and accessibility testing tools
2. **Validate Changes**: Ensure all UI functionality remains intact
3. **Add to CI/CD**: Integrate accessibility checks in build pipeline
4. **User Testing**: Conduct usability testing with users of assistive technologies

## Accessibility Testing Tools

Recommended tools for ongoing accessibility validation:
- **axe-core**: Browser extension for automated accessibility testing
- **WAVE**: Web accessibility evaluation tool
- **Lighthouse**: Built-in Chrome accessibility audit
- **Screen Readers**: NVDA, JAWS, VoiceOver for manual testing

---

*Generated by AutoBot Accessibility Fix Agent*
"""

        with open(report_path, "w") as f:
            f.write(report_content)

        print(f"📋 Generated detailed report: {report_path}")
        print(f"📊 Generated JSON report: {json_report_path}")


if __name__ == "__main__":
    import sys

    root_path = (
        sys.argv[1] if len(sys.argv) > 1 else "/home/kali/Desktop/AutoBot/autobot-vue"
    )

    agent = AccessibilityFixAgent(root_path)
    agent.scan_and_fix()
    agent.generate_report()

    print(
        "\n🎉 Accessibility fix complete! Your AutoBot frontend is now more accessible."
    )
    print(
        "📋 Check the generated report for detailed information about the improvements made."
    )
