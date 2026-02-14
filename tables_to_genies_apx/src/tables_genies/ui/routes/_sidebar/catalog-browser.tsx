import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import customInstance from '@/lib/axios-instance';

export const Route = createFileRoute('/_sidebar/catalog-browser')({
  component: CatalogBrowser,
});

function CatalogBrowser() {
  const [selectedTables, setSelectedTables] = useState<string[]>([]);
  const navigate = useNavigate();

  const { data: catalogs, isLoading, isError, error } = useQuery({
    queryKey: ['listCatalogs'],
    queryFn: async () => {
      const response = await customInstance({ url: '/uc/catalogs', method: 'GET' });
      return response;
    },
  });

  if (isLoading) {
    return (
      <div className="p-8">
        <h1 className="text-3xl font-bold mb-6">Browse Catalogs</h1>
        <p className="text-slate-600 dark:text-slate-400">Loading catalogs...</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="p-8">
        <h1 className="text-3xl font-bold mb-6 text-red-600">Error</h1>
        <p className="text-red-600 dark:text-red-400 mb-4">
          Failed to load catalogs: {error instanceof Error ? error.message : String(error)}
        </p>
        <button
          onClick={() => window.location.reload()}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold mb-6">Browse Catalogs</h1>

      {!catalogs || catalogs.length === 0 ? (
        <p className="text-slate-600 dark:text-slate-400">No catalogs found</p>
      ) : (
        <div className="border border-slate-200 dark:border-slate-700 rounded-lg">
          <div className="divide-y divide-slate-200 dark:divide-slate-700">
            {catalogs.slice(0, 5).map((catalog: any) => (
              <div key={catalog.name} className="p-4 hover:bg-slate-50 dark:hover:bg-slate-900">
                <h2 className="font-semibold text-slate-900 dark:text-slate-100">{catalog.name}</h2>
                <p className="text-sm text-slate-600 dark:text-slate-400">{catalog.comment || '(no description)'}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-8 flex gap-4">
        <button
          onClick={() => navigate({ to: '/enrichment' })}
          disabled={selectedTables.length === 0}
          className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Next: Enrich Tables →
        </button>
      </div>

      <div className="mt-4 text-sm text-slate-600 dark:text-slate-400">
        Selected: {selectedTables.length} tables
      </div>
    </div>
  );
}
