import React, { useEffect } from "react";
import { AppProvider, useApp } from "./store/appStore";
import { ToastProvider, onUnauthorizedBridge } from "./bridges";
import { Layout } from "./components/Layout";
import { PosPage } from "./pages/PosPage";
import { SalesPage } from "./pages/SalesPage";
import { ShiftsPage } from "./pages/ShiftsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { BranchesPage } from "./pages/BranchesPage";
import { InventoryPage } from "./pages/InventoryPage";
import { CustomersPage } from "./pages/CustomersPage";
import { ExpensesPage } from "./pages/ExpensesPage";
import { ReportsPage } from "./pages/ReportsPage";
import { UsersPage } from "./pages/UsersPage";

function Router() {
  const app = useApp();
  useEffect(() => onUnauthorizedBridge(() => app.setUser(null)), [app]);
  switch (app.page) {
    case "pos": return <PosPage />;
    case "sales": return <SalesPage />;
    case "shifts": return <ShiftsPage />;
    case "dashboard": return <DashboardPage />;
    case "branches": return <BranchesPage />;
    case "inventory": return <InventoryPage />;
    case "customers": return <CustomersPage />;
    case "expenses": return <ExpensesPage />;
    case "reports": return <ReportsPage />;
    case "users": return <UsersPage />;
    default: return <PosPage />;
  }
}

export default function App() {
  return (
    <ToastProvider>
      <AppProvider>
        <Layout>
          <Router />
        </Layout>
      </AppProvider>
    </ToastProvider>
  );
}
