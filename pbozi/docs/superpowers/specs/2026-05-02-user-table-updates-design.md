# Design - User Table Updates

## Overview
Update the `UserTable` component in the admin panel to provide more information (Phone number) and a direct action (Message) for each user.

## Requirements
- Add a "Phone" column to the `UserTable`.
- Display `user.phone_number` in the new column.
- Add a "Message" button in the "Actions" column.
- The "Message" button should link to `/messaging?userId=[IDENTIFIER]`.
- Identifier should be `user.telegram_user_id` (if available) or `user.id`.

## Architecture & Components
- **Component**: `frontend-v2/src/components/users/UserTable.tsx`
- **Icon**: `Send` from `lucide-react`.

## Implementation Details
- **Header**: Add `<th>Phone</th>` before "Actions".
- **Body**: Add `<td>{user.phone_number || '-'}</td>` before the "Actions" cell.
- **Actions**: Add a new `<button>` with the `Send` icon and "Message" text.
- **Navigation**: Use `window.location.href` for navigation to `/messaging`.

## Testing Strategy
- Manual verification of the table layout.
- Verify the "Message" button correctly constructs the URL.
- Verify the "Phone" column displays the correct data or '-' if null.
