'use client';

import {
  Children,
  type ReactElement,
  type ReactNode,
  isValidElement,
  useCallback,
  useMemo,
  useState,
} from 'react';

const PAGE_SIZE = 25;

function extractChildren(node: ReactNode): ReactNode[] {
  if (!isValidElement(node)) return [];
  return Children.toArray((node as ReactElement).props.children);
}

export function PaginatedTable(props: { children?: ReactNode }) {
  const { thead, rows } = useMemo(() => {
    const kids = Children.toArray(props.children);
    let thead: ReactNode = null;
    let bodyRows: ReactNode[] = [];
    for (const child of kids) {
      if (!isValidElement(child)) continue;
      const tag =
        typeof child.type === 'string' ? child.type : '';
      if (tag === 'thead') {
        thead = child;
      } else if (tag === 'tbody') {
        bodyRows = extractChildren(child);
      }
    }
    return { thead, rows: bodyRows };
  }, [props.children]);

  const totalRows = rows.length;
  const needsPagination = totalRows > PAGE_SIZE;
  const totalPages = Math.ceil(totalRows / PAGE_SIZE);

  const [page, setPage] = useState(0);

  const handlePrev = useCallback(() => setPage((p) => Math.max(0, p - 1)), []);
  const handleNext = useCallback(
    () => setPage((p) => Math.min(totalPages - 1, p + 1)),
    [totalPages],
  );

  const visibleRows = needsPagination
    ? rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
    : rows;

  const startRow = page * PAGE_SIZE + 1;
  const endRow = Math.min((page + 1) * PAGE_SIZE, totalRows);

  return (
    <div data-streamdown="table-wrapper" className="overflow-x-auto">
      <table>
        {thead}
        <tbody>{visibleRows}</tbody>
      </table>
      {needsPagination && (
        <div className="flex items-center justify-between border-t border-zinc-200 px-2 py-1.5 text-xs text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
          <span>
            Rows {startRow}–{endRow} of {totalRows}
          </span>
          <div className="flex gap-1">
            <button
              type="button"
              onClick={handlePrev}
              disabled={page === 0}
              className="rounded px-2 py-0.5 hover:bg-zinc-100 disabled:opacity-40 dark:hover:bg-zinc-800"
            >
              Prev
            </button>
            <button
              type="button"
              onClick={handleNext}
              disabled={page >= totalPages - 1}
              className="rounded px-2 py-0.5 hover:bg-zinc-100 disabled:opacity-40 dark:hover:bg-zinc-800"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
