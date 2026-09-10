import { ReactNode } from 'react';

export interface PageContainerProps {
  children: ReactNode;
}

/** The consistent max-width/padding wrapper every page renders its
 * content inside — see tokens.css's `--width-content`. */
export function PageContainer({ children }: PageContainerProps) {
  return <div className="mx-auto flex w-full max-w-(--width-content) flex-col gap-6 p-6">{children}</div>;
}
