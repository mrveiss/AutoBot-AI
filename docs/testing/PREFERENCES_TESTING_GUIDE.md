# AutoBot Preferences System - Testing Guide

**Issue**: #753 - Dark/Light Mode Refinement & Additional Customization
**Version**: 1.0.0
**Last Updated**: 2026-02-05
**Status**: Ready for Testing

---

## Overview

This guide provides comprehensive testing procedures for the AutoBot Preferences System, including dark/light mode, font size scaling, accent colors, and layout density preferences.

**Test URL**: http://172.16.168.21:5173/preferences

---

## Table of Contents

1. [Quick Start Testing](#quick-start-testing)
2. [Functional Testing](#functional-testing)
3. [Accessibility Testing](#accessibility-testing)
4. [Cross-Browser Testing](#cross-browser-testing)
5. [Mobile Testing](#mobile-testing)
6. [Performance Testing](#performance-testing)
7. [Persistence Testing](#persistence-testing)
8. [Integration Testing](#integration-testing)

---

## Quick Start Testing

### Prerequisites
- AutoBot frontend running at http://172.16.168.21:5173
- Modern web browser (Chrome, Firefox, Safari, or Edge)
- Screen reader (optional, for accessibility testing)

### Basic Smoke Test (5 minutes)

1. **Navigate to Preferences**
   - Go to http://172.16.168.21:5173
   - Click "Preferences" in the header
   - Verify page loads successfully

2. **Test Dark Mode Toggle**
   - Click dark mode toggle in header
   - Verify theme changes immediately
   - Toggle back to light mode
   - Verify theme switches back

3. **Test Font Size**
   - Click "Small" font size button
   - Verify text gets smaller across the page
   - Click "Large" font size button
   - Verify text gets larger

4. **Test Accent Color**
   - Click each color option (Teal, Emerald, Blue, Purple, Orange)
   - Verify primary color changes throughout UI
   - Check buttons, links, and highlights

5. **Test Layout Density**
   - Click "Compact" - verify spacing reduces
   - Click "Spacious" - verify spacing increases
   - Click "Comfortable" - verify default spacing

6. **Test Persistence**
   - Change all preferences
   - Refresh the page (F5)
   - Verify all preferences are retained

✅ **Expected Result**: All preferences work and persist after refresh

---

## Functional Testing

### Test Suite 1: Dark/Light Mode

#### TC-DM-01: Toggle Dark Mode
**Steps:**
1. Start in light mode
2. Click dark mode toggle in header
3. Observe theme change

**Expected:**
- Background changes to dark (#0F172A)
- Text changes to light (#F8FAFC)
- Primary color adjusts to lighter teal (#2DD4BF)
- Transition is smooth (0.3s)

**Pass/Fail**: ⬜

---

#### TC-DM-02: System Preference Detection
**Steps:**
1. Clear localStorage: `localStorage.clear()`
2. Set OS to dark mode
3. Reload AutoBot
4. Observe initial theme

**Expected:**
- AutoBot starts in dark mode automatically
- No flash of wrong theme (FOUC)

**Pass/Fail**: ⬜

---

#### TC-DM-03: Preference Override
**Steps:**
1. OS set to dark mode
2. Toggle to light mode in AutoBot
3. Reload page

**Expected:**
- AutoBot stays in light mode (user preference overrides OS)
- localStorage contains `theme: "light"`

**Pass/Fail**: ⬜

---

### Test Suite 2: Font Size Preferences

#### TC-FS-01: Small Font Size
**Steps:**
1. Navigate to Preferences
2. Click "Small" button
3. Navigate to different pages (Chat, Knowledge, Analytics)

**Expected:**
- All text scales down proportionally
- Base font: 15px (0.9375rem)
- Headings scale: 22px, 19px, 17px
- No layout breaks

**Pass/Fail**: ⬜

---

#### TC-FS-02: Large Font Size
**Steps:**
1. Navigate to Preferences
2. Click "Large" button
3. Navigate to different pages

**Expected:**
- All text scales up proportionally
- Base font: 17px (1.0625rem)
- Headings scale: 32px, 26px, 21px
- No overflow issues

**Pass/Fail**: ⬜

---

#### TC-FS-03: Font Size Persistence
**Steps:**
1. Set font to "Large"
2. Navigate to Chat
3. Refresh page
4. Check font size

**Expected:**
- Font remains "Large" after refresh
- No flash of default size

**Pass/Fail**: ⬜

---

### Test Suite 3: Accent Colors

#### TC-AC-01: Teal Accent (Default)
**Steps:**
1. Select "Teal" accent color
2. Check primary buttons, links, highlights

**Expected:**
- Light mode: #0D9488
- Dark mode: #2DD4BF
- Applies to all primary UI elements

**Pass/Fail**: ⬜

---

#### TC-AC-02: Emerald Accent
**Steps:**
1. Select "Emerald"
2. Navigate to different pages

**Expected:**
- Light mode: #10B981
- Dark mode: #34D399
- Consistent across all pages

**Pass/Fail**: ⬜

---

#### TC-AC-03: Blue Accent
**Steps:**
1. Select "Blue"
2. Check all primary UI elements

**Expected:**
- Light mode: #3B82F6
- Dark mode: #60A5FA
- Proper contrast ratios maintained

**Pass/Fail**: ⬜

---

#### TC-AC-04: Purple Accent
**Steps:**
1. Select "Purple"
2. Toggle dark mode

**Expected:**
- Light mode: #8B5CF6
- Dark mode: #A78BFA
- Color adjusts properly with theme

**Pass/Fail**: ⬜

---

#### TC-AC-05: Orange Accent
**Steps:**
1. Select "Orange"
2. Check readability

**Expected:**
- Light mode: #F97316
- Dark mode: #FB923C
- Text remains readable on colored backgrounds

**Pass/Fail**: ⬜

---

### Test Suite 4: Layout Density

#### TC-LD-01: Compact Density
**Steps:**
1. Select "Compact" density
2. Navigate to Knowledge Base
3. Check spacing

**Expected:**
- Reduced padding: 12px (--spacing-md)
- Tighter line spacing
- More content visible per screen
- No overlapping elements

**Pass/Fail**: ⬜

---

#### TC-LD-02: Spacious Density
**Steps:**
1. Select "Spacious" density
2. Navigate to Analytics
3. Check spacing

**Expected:**
- Increased padding: 24px (--spacing-md)
- Generous line spacing
- More breathing room
- Improved readability

**Pass/Fail**: ⬜

---

#### TC-LD-03: Comfortable Density (Default)
**Steps:**
1. Select "Comfortable"
2. Check default spacing

**Expected:**
- Balanced spacing: 16px
- Default Tailwind-compatible scale
- Optimal for most users

**Pass/Fail**: ⬜

---

### Test Suite 5: Reset Functionality

#### TC-RF-01: Reset All Preferences
**Steps:**
1. Change all preferences to non-defaults:
   - Font: Large
   - Color: Orange
   - Density: Compact
   - Theme: Dark
2. Click "Reset" button
3. Observe changes

**Expected:**
- Font: Medium
- Color: Teal
- Density: Comfortable
- Theme: Unchanged (dark mode is separate)
- localStorage cleared for preferences

**Pass/Fail**: ⬜

---

## Accessibility Testing

### Test Suite 6: Screen Reader Testing

**Tools**: NVDA (Windows), JAWS (Windows), VoiceOver (Mac)

#### TC-SR-01: Preferences Panel Navigation
**Steps:**
1. Enable screen reader
2. Tab to Preferences page
3. Navigate through all controls

**Expected Announcements:**
- "Preferences, heading level 1"
- "Font Size, group"
- "Set font size to Small, button, not pressed"
- "Set font size to Medium, button, pressed" (if active)
- "Accent Color, group"
- "Set accent color to Teal, button, pressed"
- "Layout Density, group"

**Pass/Fail**: ⬜

---

#### TC-SR-02: Preference Change Announcements
**Steps:**
1. Enable screen reader
2. Click "Large" font size button

**Expected:**
- Button announces: "Set font size to Large, button, pressed"
- Live region announces: "Font size changed to Large"

**Pass/Fail**: ⬜

---

#### TC-SR-03: Form Semantics
**Steps:**
1. Inspect with screen reader
2. Navigate through form structure

**Expected:**
- "Preferences, form"
- "Font Size, group" (fieldset/legend)
- Proper form landmark navigation

**Pass/Fail**: ⬜

---

### Test Suite 7: Keyboard Navigation

#### TC-KN-01: Tab Navigation
**Steps:**
1. Click in address bar
2. Press Tab repeatedly
3. Navigate through all preferences

**Expected:**
- Logical tab order
- Visible focus indicators (blue outline)
- All interactive elements reachable
- No keyboard traps

**Pass/Fail**: ⬜

---

#### TC-KN-02: Enter Key Activation
**Steps:**
1. Tab to font size button
2. Press Enter key

**Expected:**
- Button activates
- Preference changes
- Focus remains on button
- Screen reader announces change

**Pass/Fail**: ⬜

---

#### TC-KN-03: Space Key Activation
**Steps:**
1. Tab to accent color button
2. Press Space key

**Expected:**
- Button activates
- Color changes immediately
- No page scroll (preventDefault working)

**Pass/Fail**: ⬜

---

### Test Suite 8: ARIA Compliance

#### TC-ARIA-01: ARIA Labels
**Steps:**
1. Inspect with browser DevTools
2. Check all buttons

**Expected ARIA attributes:**
```html
<button
  aria-label="Set font size to Small"
  aria-pressed="false"
  role="button"
>
```

**Pass/Fail**: ⬜

---

#### TC-ARIA-02: Live Regions
**Steps:**
1. Inspect DOM
2. Find announcement element

**Expected:**
```html
<div
  role="status"
  aria-live="polite"
  aria-atomic="true"
  class="sr-only"
>
```

**Pass/Fail**: ⬜

---

## Cross-Browser Testing

### Test Suite 9: Browser Compatibility

#### TC-BC-01: Chrome/Chromium
- Version: Latest
- OS: Windows/Linux/Mac
- **Features to Test**: All preferences, localStorage, CSS variables
- **Pass/Fail**: ⬜

#### TC-BC-02: Firefox
- Version: Latest
- OS: Windows/Linux/Mac
- **Features to Test**: All preferences, localStorage, CSS variables
- **Pass/Fail**: ⬜

#### TC-BC-03: Safari
- Version: Latest
- OS: Mac/iOS
- **Features to Test**: All preferences, localStorage, CSS variables
- **Pass/Fail**: ⬜

#### TC-BC-04: Edge
- Version: Latest
- OS: Windows
- **Features to Test**: All preferences, localStorage, CSS variables
- **Pass/Fail**: ⬜

---

## Mobile Testing

### Test Suite 10: Mobile Devices

#### TC-MOB-01: Touch Targets
**Steps:**
1. Open on mobile device
2. Try tapping all buttons

**Expected:**
- All buttons minimum 44px tap target
- No mis-taps
- Comfortable spacing for fingers

**Pass/Fail**: ⬜

---

#### TC-MOB-02: Responsive Layout
**Steps:**
1. Test on phone (320px - 768px)
2. Check layout adjustments

**Expected:**
- Font size buttons stack vertically
- Color grid shows 2 columns
- No horizontal scroll
- Text remains readable

**Pass/Fail**: ⬜

---

#### TC-MOB-03: Mobile Navigation
**Steps:**
1. Open mobile menu
2. Navigate to Preferences

**Expected:**
- Preferences link visible in mobile menu
- Correct icon displayed
- Menu closes after navigation

**Pass/Fail**: ⬜

---

## Performance Testing

### Test Suite 11: Performance Metrics

#### TC-PERF-01: Preference Change Speed
**Steps:**
1. Open DevTools Performance tab
2. Click different preferences rapidly
3. Measure change time

**Expected:**
- Theme change: < 50ms
- Font size change: < 50ms
- Instant visual feedback
- No layout thrashing

**Pass/Fail**: ⬜

---

#### TC-PERF-02: Page Load with Preferences
**Steps:**
1. Set all preferences to non-defaults
2. Hard refresh (Ctrl+Shift+R)
3. Measure load time

**Expected:**
- No FOUC (Flash of Unstyled Content)
- Preferences apply immediately
- No flash of default theme
- Total load time increase < 50ms

**Pass/Fail**: ⬜

---

## Persistence Testing

### Test Suite 12: LocalStorage Persistence

#### TC-LS-01: Single Preference Persistence
**Steps:**
1. Change font size to "Large"
2. Close tab
3. Open new tab to AutoBot
4. Check font size

**Expected:**
- Font size remains "Large"
- localStorage key exists: `autobot-preferences`
- Value: `{"fontSize":"large","accentColor":"teal","layoutDensity":"comfortable"}`

**Pass/Fail**: ⬜

---

#### TC-LS-02: Multiple Preferences Persistence
**Steps:**
1. Change all preferences
2. Navigate to different pages
3. Refresh
4. Check all preferences

**Expected:**
- All preferences retained
- Consistent across all pages
- No reset to defaults

**Pass/Fail**: ⬜

---

#### TC-LS-03: Private/Incognito Mode
**Steps:**
1. Open in private/incognito window
2. Change preferences
3. Close and reopen private window

**Expected:**
- Preferences work during session
- Reset after closing (expected behavior)
- No errors in console

**Pass/Fail**: ⬜

---

## Integration Testing

### Test Suite 13: Cross-Feature Integration

#### TC-INT-01: Preferences + Dark Mode
**Steps:**
1. Set accent to "Purple"
2. Toggle dark mode
3. Check color adaptation

**Expected:**
- Purple light (#8B5CF6) → Purple dark (#A78BFA)
- Automatic color adjustment
- Maintained contrast

**Pass/Fail**: ⬜

---

#### TC-INT-02: Preferences + Navigation
**Steps:**
1. Set preferences
2. Navigate: Chat → Knowledge → Analytics → Preferences
3. Check consistency

**Expected:**
- Preferences apply on all pages
- No reset during navigation
- Consistent visual appearance

**Pass/Fail**: ⬜

---

#### TC-INT-03: Preferences + Responsive
**Steps:**
1. Set font to "Small", density to "Compact"
2. Resize browser 1920px → 768px → 375px
3. Check layout

**Expected:**
- Responsive breakpoints work
- Font size preference maintained
- Density preference maintained
- No layout breaks

**Pass/Fail**: ⬜

---

## Test Execution Checklist

### Before Testing
- [ ] Frontend server running (http://172.16.168.21:5173)
- [ ] Clear browser cache
- [ ] Clear localStorage
- [ ] Browser DevTools open

### During Testing
- [ ] Record all failures
- [ ] Take screenshots of issues
- [ ] Note browser/OS versions
- [ ] Check console for errors

### After Testing
- [ ] Document all bugs found
- [ ] Create GitHub issues for failures
- [ ] Update test results below
- [ ] Sign off on test completion

---

## Test Results Summary

**Test Date**: _____________
**Tester Name**: _____________
**Browser**: _____________
**OS**: _____________

| Test Suite | Tests Run | Passed | Failed | Skipped |
|-----------|-----------|--------|--------|---------|
| Dark/Light Mode | 3 | __ | __ | __ |
| Font Size | 3 | __ | __ | __ |
| Accent Colors | 5 | __ | __ | __ |
| Layout Density | 3 | __ | __ | __ |
| Reset Functionality | 1 | __ | __ | __ |
| Screen Reader | 3 | __ | __ | __ |
| Keyboard Navigation | 3 | __ | __ | __ |
| ARIA Compliance | 2 | __ | __ | __ |
| Browser Compatibility | 4 | __ | __ | __ |
| Mobile Testing | 3 | __ | __ | __ |
| Performance | 2 | __ | __ | __ |
| Persistence | 3 | __ | __ | __ |
| Integration | 3 | __ | __ | __ |
| **TOTAL** | **38** | **__** | **__** | **__** |

**Overall Pass Rate**: ____%

---

## Known Issues

### Issue Tracker
| ID | Description | Severity | Status |
|----|-------------|----------|--------|
| - | No known issues | - | - |

---

## Sign-Off

**Developer**: mrveiss
**QA Lead**: _____________
**Product Owner**: _____________

**Status**:
- [ ] All tests passed
- [ ] Tests passed with minor issues (documented)
- [ ] Tests failed (blocking issues found)

**Approved for Production**: ☐ Yes ☐ No

**Date**: _____________

---

## Appendix

### A. Testing Tools

**Recommended Tools:**
- **Accessibility**: axe DevTools, WAVE, Lighthouse
- **Screen Readers**: NVDA, JAWS, VoiceOver
- **Cross-Browser**: BrowserStack, LambdaTest
- **Performance**: Chrome DevTools, WebPageTest
- **Mobile**: Chrome DevTools Device Mode, real devices

### B. Useful Commands

**Clear localStorage:**
```javascript
localStorage.clear()
```

**Inspect preferences:**
```javascript
console.log(JSON.parse(localStorage.getItem('autobot-preferences')))
```

**Force theme:**
```javascript
document.documentElement.setAttribute('data-theme', 'dark')
```

**Check applied styles:**
```javascript
getComputedStyle(document.documentElement).getPropertyValue('--color-primary')
```

### C. Accessibility Resources

- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/)
- [WebAIM Resources](https://webaim.org/resources/)

---

**Document Version**: 1.0.0
**Last Updated**: 2026-02-05
**Maintained By**: AutoBot Development Team
