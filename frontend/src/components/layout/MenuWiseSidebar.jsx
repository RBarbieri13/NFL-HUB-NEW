import React from 'react';
import { NavLink } from 'react-router-dom';
import { BarChart3, TrendingUp, Filter } from 'lucide-react';

const MenuWiseSidebar = ({ activeRoute, onNavigate }) => {
  return (
    <aside className="h-full bg-slate-50 border-r border-slate-200 flex flex-col">
      {/* Sidebar Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-sm shadow-emerald-500/50"></div>
          <span className="font-semibold text-slate-700 text-sm">MenuWise</span>
        </div>
      </div>

      {/* Primary Navigation */}
      <nav className="px-3 py-4">
        <div className="space-y-1">
          <NavLink
            to="/data-table"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-blue-50 text-blue-700 border border-blue-200'
                  : 'text-slate-600 hover:bg-slate-100 border border-transparent'
              }`
            }
          >
            <BarChart3 className="h-4 w-4" />
            <span>Data Table</span>
          </NavLink>

          <NavLink
            to="/trend-tool"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-blue-50 text-blue-700 border border-blue-200'
                  : 'text-slate-600 hover:bg-slate-100 border border-transparent'
              }`
            }
          >
            <TrendingUp className="h-4 w-4" />
            <span>Trend Tool</span>
          </NavLink>
        </div>
      </nav>

      {/* Filter Card Placeholder - Temporarily hidden to avoid double sidebar appearance */}
      {/* Will be re-enabled when filters are migrated from main content area */}
      <div className="px-3 flex-1 overflow-auto border-t border-slate-200">
        {/* Placeholder removed - filters still in main content area */}
      </div>

      {/* Footer Placeholder */}
      <div className="px-3 py-3 border-t border-slate-200 bg-slate-50/50">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-500">Footer (Placeholder)</span>
        </div>
      </div>
    </aside>
  );
};

export default MenuWiseSidebar;
