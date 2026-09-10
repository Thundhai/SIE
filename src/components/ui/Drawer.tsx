import { ReactNode } from 'react';
import { Overlay } from './Overlay';

export interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

/** A right-edge panel that keeps the underlying page visible — for
 * supporting detail (e.g. a quick view of a related record) that
 * doesn't need the user's full, blocking attention the way `Modal`
 * does. */
export function Drawer({ isOpen, onClose, title, children }: DrawerProps) {
  return (
    <Overlay isOpen={isOpen} onClose={onClose} title={title} placement="right">
      {children}
    </Overlay>
  );
}
