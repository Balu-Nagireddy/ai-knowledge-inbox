import React, { useState, useEffect, useCallback } from 'react';
import Header from './components/Header';
import IngestBox from './components/IngestBox';
import KnowledgeInbox from './components/KnowledgeInbox';
import AskKnowledge from './components/AskKnowledge';
import { fetchHealth, fetchItems, deleteItem } from './api';

export default function App() {
  const [health, setHealth] = useState(null);
  const [items, setItems] = useState([]);
  const [loadingItems, setLoadingItems] = useState(true);

  const loadHealth = useCallback(async () => {
    const data = await fetchHealth();
    setHealth(data);
  }, []);

  const loadItems = useCallback(async () => {
    try {
      setLoadingItems(true);
      const data = await fetchItems();
      setItems(data);
    } catch (err) {
      console.error('Failed to load items:', err);
    } finally {
      setLoadingItems(false);
    }
  }, []);

  useEffect(() => {
    loadHealth();
    loadItems();
    const interval = setInterval(loadHealth, 15000);
    return () => clearInterval(interval);
  }, [loadHealth, loadItems]);

  const handleItemIngested = (newItem) => {
    // Prepend or refresh
    loadItems();
  };

  const handleDeleteItem = async (itemId) => {
    try {
      await deleteItem(itemId);
      setItems((prev) => prev.filter((i) => i.id !== itemId));
    } catch (err) {
      alert(`Failed to delete item: ${err.message}`);
    }
  };

  return (
    <div className="app-container">
      <Header health={health} />

      <main className="main-grid">
        <section className="left-column">
          <IngestBox onItemIngested={handleItemIngested} />
          <KnowledgeInbox
            items={items}
            loading={loadingItems}
            onRefresh={loadItems}
            onDeleteItem={handleDeleteItem}
          />
        </section>

        <section className="right-column">
          <AskKnowledge itemsCount={items.length} />
        </section>
      </main>
    </div>
  );
}
