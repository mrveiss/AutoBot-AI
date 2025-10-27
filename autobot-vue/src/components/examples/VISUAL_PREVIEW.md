# Visual Preview - AsyncOperationExample Component

A text-based preview of how the component will look when rendered in the browser.

## Component Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    useAsyncOperation Examples                            │
│        Practical demonstrations of the async operation composable       │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ Example 1: Simple Async Operation        [15 lines → 7 lines (53%)]    │
├─────────────────────────────────────────────────────────────────────────┤
│ Basic health check with automatic loading and error state management    │
│                                                                          │
│ [ Check Health ]                                                         │
│                                                                          │
│ ┌──────────────────────────────────────────────────────────────┐       │
│ │ ⟳ Checking backend health...                                 │       │
│ └──────────────────────────────────────────────────────────────┘       │
│                                                                          │
│ ▼ View Before/After Code                                               │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ Example 2: Success Callback              [22 lines → 9 lines (59%)]    │
├─────────────────────────────────────────────────────────────────────────┤
│ Save settings with automatic notification on success                    │
│                                                                          │
│ Setting Value: [_________________________]                              │
│                                                                          │
│ [ Save Settings ]                                                        │
│                                                                          │
│ ┌──────────────────────────────────────────────────────────────┐       │
│ │ ✓ Settings saved successfully!                               │       │
│ └──────────────────────────────────────────────────────────────┘       │
│                                                                          │
│ ▼ View Before/After Code                                               │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ Example 3: Custom Error Handling         [25 lines → 11 lines (56%)]   │
├─────────────────────────────────────────────────────────────────────────┤
│ Validate configuration with custom error logging and recovery           │
│                                                                          │
│ [ Validate Configuration ]                                               │
│                                                                          │
│ ┌──────────────────────────────────────────────────────────────┐       │
│ │ ✗ Validation Failed: Configuration validation failed         │       │
│ └──────────────────────────────────────────────────────────────┘       │
│                                                                          │
│ Error Log:                                                              │
│ • 2025-10-27T09:42:15.123Z  Configuration validation failed             │
│                                                                          │
│ ▼ View Before/After Code                                               │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ Example 4: Multiple Concurrent Operations [40 lines → 18 lines (55%)]  │
├─────────────────────────────────────────────────────────────────────────┤
│ Load users and system info concurrently using createAsyncOperations     │
│                                                                          │
│ [ Load All Data ]                                                        │
│                                                                          │
│ ┌───────────────────────────┐ ┌───────────────────────────┐           │
│ │ Users                      │ │ System Info                │           │
│ ├───────────────────────────┤ ├───────────────────────────┤           │
│ │ ⟳ Loading users...        │ │ ⟳ Loading system info...  │           │
│ └───────────────────────────┘ └───────────────────────────┘           │
│                                                                          │
│ ▼ View Before/After Code                                               │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ Example 5: Data Transformation           [30 lines → 12 lines (60%)]   │
├─────────────────────────────────────────────────────────────────────────┤
│ Fetch analytics data and transform for visualization                    │
│                                                                          │
│ [ Load Analytics ]                                                       │
│                                                                          │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                   │
│ │  Total   │ │ Avg Resp │ │  Error   │ │ Success  │                   │
│ │ Requests │ │   Time   │ │   Rate   │ │   Rate   │                   │
│ │  1,250   │ │  343ms   │ │  1.84%   │ │  98.16%  │                   │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘                   │
│                                                                          │
│ ▼ View Before/After Code                                               │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         Pattern Benefits                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│ ┌────────────────┐ ┌────────────────┐ ┌────────────────┐              │
│ │ 📉 57% Code    │ │ 🎯 Consistent  │ │ 🔒 Type Safety │              │
│ │    Reduction   │ │    Pattern     │ │                │              │
│ │ 132→57 lines   │ │ Standardized   │ │ Full TypeScript│              │
│ └────────────────┘ └────────────────┘ └────────────────┘              │
│                                                                          │
│ ┌────────────────┐ ┌────────────────┐ ┌────────────────┐              │
│ │ 🧪 Easier      │ │ 🔄 Automatic   │ │ 🎨 Cleaner     │              │
│ │    Testing     │ │    State       │ │    Templates   │              │
│ │ Mock execute() │ │ Loading/error  │ │ Use isSuccess  │              │
│ └────────────────┘ └────────────────┘ └────────────────┘              │
└─────────────────────────────────────────────────────────────────────────┘
```

## Expanded Code Section Preview

When user clicks "View Before/After Code":

```
▼ View Before/After Code

┌─────────────────────────────────┬─────────────────────────────────┐
│ ❌ Before (15 lines)             │ ✅ After (7 lines)              │
├─────────────────────────────────┼─────────────────────────────────┤
│ // Manual state management      │ // Automatic state management   │
│ const loading = ref(false)      │ const health = useAsyncOp({     │
│ const error = ref(null)         │   errorMessage: 'Failed...'     │
│ const healthData = ref(null)    │ })                              │
│                                 │                                 │
│ const checkHealth = async () => │ const checkHealth = () =>       │
│   loading.value = true          │   health.execute(async () => {  │
│   error.value = null            │     const res = await fetch()   │
│   try {                         │     return res.json()           │
│     const res = await fetch()   │   })                            │
│     healthData.value = ...      │                                 │
│   } catch (err) {               │                                 │
│     error.value = err           │                                 │
│   } finally {                   │                                 │
│     loading.value = false       │                                 │
│   }                             │                                 │
│ }                               │                                 │
└─────────────────────────────────┴─────────────────────────────────┘
```

## Color Scheme

The component uses AutoBot's color palette:

- **Primary**: Blue (#3b82f6) - Buttons, links
- **Success**: Green (#10b981) - Success messages, benefits
- **Error**: Red (#ef4444) - Error messages
- **Loading**: Light Blue (#eff6ff) - Loading indicators
- **Background**: Light Gray (#f8f9fa) - Page background
- **Cards**: White (#ffffff) - Component cards
- **Text**: Blueish Gray (#1e3a8a, #6b7280) - Headers, body
- **Gradient**: Purple-Blue gradient - Summary card

## Animations

1. **Loading Spinner**: Rotating circle animation (800ms)
2. **Success Toast**: Slide in from right (300ms)
3. **Expandable Sections**: Smooth height transition
4. **Button Hover**: Subtle color darkening
5. **Card Hover**: Slight upward translation (-4px)

## Responsive Breakpoints

### Desktop (1920x1080)
- 2-column grid for data sections
- 3-column grid for benefits
- Full-width code comparisons

### Laptop (1366x768)
- 2-column grid maintained
- Slightly reduced padding
- Full-width maintained

### Tablet (768x1024)
- Single column for data sections
- 2-column grid for benefits
- Side-by-side code comparisons become stacked

### Mobile (375x667)
- All single column
- Benefits cards full width
- Code sections full width
- Reduced font sizes

## Interactive Elements

1. **Buttons**
   - Hover: Darken color
   - Disabled: 50% opacity, no pointer
   - Loading: Show "Loading..." text
   - Click: Execute async operation

2. **Expandable Sections**
   - Click summary to expand/collapse
   - Arrow icon rotates
   - Smooth height animation

3. **Error Log**
   - Scrollable if many entries
   - Each entry has timestamp + message
   - Persists across operations

4. **Reset Buttons**
   - Appear only when data/error exists
   - Clear all state on click
   - Gray styling (secondary action)

5. **Form Inputs**
   - Blue focus ring
   - Disabled when loading
   - Real-time validation (required)

## Accessibility Features

1. **Semantic HTML**
   - Proper heading hierarchy (h1 → h2 → h3 → h4)
   - Descriptive button text
   - Form labels with for/id

2. **Keyboard Navigation**
   - All buttons focusable
   - Tab order logical
   - Enter key activates buttons

3. **Screen Reader Support**
   - ARIA labels on icons
   - Loading state announced
   - Error messages announced

4. **Color Contrast**
   - All text meets WCAG AA standards
   - Error messages high contrast
   - Button text clearly visible

## Loading States

Each example shows different loading patterns:

1. **Spinner + Text**: "Checking backend health..."
2. **Button Disabled**: Button shows "Saving..." text
3. **Section Indicator**: "⟳ Loading users..."
4. **Progress Bar**: (Could be added for longer operations)

## Error States

Multiple error display patterns:

1. **Inline Error**: Red box with error message
2. **Error Log**: List of errors with timestamps
3. **Banner Error**: Full-width error notification
4. **Toast Error**: Dismissible notification (could be added)

## Success States

Various success indicators:

1. **Checkmark Icon**: ✓ with green background
2. **Success Message**: Green box with confirmation
3. **Toast Notification**: Temporary green notification
4. **Data Display**: Formatted JSON or cards

## Data Display Formats

1. **Raw JSON**: Formatted with indentation
2. **Cards**: Visual cards with labels + values
3. **Grid**: Multiple data sections side-by-side
4. **List**: Scrollable list items

## Summary Card Gradient

Beautiful gradient background for benefits section:
- Start: Purple (#667eea)
- End: Darker Purple (#764ba2)
- White text overlay
- Semi-transparent benefit cards
- Hover effect: Slight lift + brightness increase

## Typography

- **Headings**: Bold, large, blueGray color
- **Body Text**: Regular, medium, gray color
- **Code**: Monospace, smaller, dark gray
- **Labels**: Semi-bold, medium, gray color
- **Values**: Bold, large, colored by status

## Spacing

- **Page Padding**: 24px all sides
- **Card Padding**: 24px all sides
- **Section Gap**: 24px between examples
- **Element Gap**: 12-16px within sections
- **Grid Gap**: 20px between grid items

## Scrolling

- **Main Container**: Scrollable with styled scrollbar
- **Code Sections**: Horizontal scroll for long lines
- **Error Log**: Vertical scroll if many entries
- **Smooth Behavior**: All scrolling animated

This preview gives you a visual understanding of how the component will appear and behave when rendered in a browser!
