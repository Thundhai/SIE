import { ChevronRight } from 'lucide-react';
import { Fragment } from 'react';
import { Link } from 'react-router-dom';

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

export interface BreadcrumbProps {
  items: BreadcrumbItem[];
}

/** An accessible breadcrumb trail — `nav[aria-label="Breadcrumb"]`, an
 * ordered list, and `aria-current="page"` on the final (current) item. */
export function Breadcrumb({ items }: BreadcrumbProps) {
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex flex-wrap items-center gap-1.5 text-sm text-text-secondary">
        {items.map((item, index) => {
          const isLast = index === items.length - 1;
          return (
            <Fragment key={item.label}>
              {index > 0 && <ChevronRight className="h-3.5 w-3.5 text-text-muted" aria-hidden="true" />}
              <li>
                {item.href && !isLast ? (
                  <Link to={item.href} className="hover:text-text-primary hover:underline">
                    {item.label}
                  </Link>
                ) : (
                  <span aria-current={isLast ? 'page' : undefined} className={isLast ? 'font-medium text-text-primary' : undefined}>
                    {item.label}
                  </span>
                )}
              </li>
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
