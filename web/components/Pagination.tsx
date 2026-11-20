'use client';

/**
 * Shared pagination control.
 *
 * Lists that can hold thousands of rows (documents, claims, wiki subjects) must
 * not render everything: it is slow to fetch, slow to lay out, and useless to
 * read. Every such list uses this.
 */

import styles from './Pagination.module.css';

interface PaginationProps {
  page: number;            // 1-based
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
  pageSizeOptions?: number[];
}

export default function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [25, 50, 100, 200],
}: PaginationProps) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  // Window of page numbers around the current page.
  const windowSize = 5;
  let start = Math.max(1, page - Math.floor(windowSize / 2));
  const end = Math.min(pageCount, start + windowSize - 1);
  start = Math.max(1, end - windowSize + 1);
  const pages: number[] = [];
  for (let i = start; i <= end; i += 1) pages.push(i);

  if (total === 0) return null;

  return (
    <div className={styles.bar}>
      <span className={styles.range}>
        {from.toLocaleString()}–{to.toLocaleString()} of {total.toLocaleString()}
      </span>

      <div className={styles.controls}>
        <button
          className={styles.btn}
          onClick={() => onPageChange(1)}
          disabled={page <= 1}
          title="First page"
        >
          «
        </button>
        <button
          className={styles.btn}
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          title="Previous page"
        >
          ‹
        </button>

        {start > 1 && <span className={styles.ellipsis}>…</span>}
        {pages.map((n) => (
          <button
            key={n}
            className={`${styles.btn} ${n === page ? styles.btnActive : ''}`}
            onClick={() => onPageChange(n)}
          >
            {n}
          </button>
        ))}
        {end < pageCount && <span className={styles.ellipsis}>…</span>}

        <button
          className={styles.btn}
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pageCount}
          title="Next page"
        >
          ›
        </button>
        <button
          className={styles.btn}
          onClick={() => onPageChange(pageCount)}
          disabled={page >= pageCount}
          title="Last page"
        >
          »
        </button>
      </div>

      {onPageSizeChange && (
        <select
          className={styles.size}
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
          aria-label="Rows per page"
        >
          {pageSizeOptions.map((n) => (
            <option key={n} value={n}>{n} / page</option>
          ))}
        </select>
      )}
    </div>
  );
}
