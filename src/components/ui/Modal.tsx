import { ReactNode } from 'react';
import { Overlay } from './Overlay';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

/** A centered, blocking overlay — for a focused single decision/detail
 * (confirmation, a short form). For a wider supporting-detail panel
 * that keeps the underlying page in view, use `Drawer` instead. */
export function Modal({ isOpen, onClose, title, children }: ModalProps) {
  return (
    <Overlay isOpen={isOpen} onClose={onClose} title={title} placement="center">
      {children}
    </Overlay>
  );
}
