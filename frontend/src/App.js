import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { AgGridReact } from 'ag-grid-react';
import { ModuleRegistry, AllCommunityModule } from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-alpine.css';
import axios from 'axios';
import { Button } from './components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './components/ui/select';
import { Badge } from './components/ui/badge';
import { Input } from './components/ui/input';
import { RefreshCw, TrendingUp, Users, Calendar, Search, Filter, Star, BarChart3, Settings, Download, DollarSign, Database, Clock, Activity, Heart, Copy, Eye, Zap } from 'lucide-react';
import { Toaster } from './components/ui/sonner';
import { toast } from 'sonner';
import OptimizerFilter from './components/OptimizerFilter';
import MenuWiseSidebar from './components/layout/MenuWiseSidebar';
import '@/App.css';

// Register AG Grid modules
ModuleRegistry.registerModules([AllCommunityModule]);

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// All NFL Teams
const NFL_TEAMS = {
  'ARI': 'Arizona Cardinals',
  'ATL': 'Atlanta Falcons',
  'BAL': 'Baltimore Ravens', 
  'BUF': 'Buffalo Bills',
  'CAR': 'Carolina Panthers',
  'CHI': 'Chicago Bears',
  'CIN': 'Cincinnati Bengals',
  'CLE': 'Cleveland Browns',
  'DAL': 'Dallas Cowboys',
  'DEN': 'Denver Broncos',
  'DET': 'Detroit Lions',
  'GB': 'Green Bay Packers',
  'HOU': 'Houston Texans',
  'IND': 'Indianapolis Colts',
  'JAX': 'Jacksonville Jaguars',
  'KC': 'Kansas City Chiefs',
  'LV': 'Las Vegas Raiders',
  'LAC': 'Los Angeles Chargers',
  'LAR': 'Los Angeles Rams',
  'MIA': 'Miami Dolphins',
  'MIN': 'Minnesota Vikings',
  'NE': 'New England Patriots',
  'NO': 'New Orleans Saints',
  'NYG': 'New York Giants',
  'NYJ': 'New York Jets',
  'PHI': 'Philadelphia Eagles',
  'PIT': 'Pittsburgh Steelers',
  'SF': 'San Francisco 49ers',
  'SEA': 'Seattle Seahawks',
  'TB': 'Tampa Bay Buccaneers',
  'TEN': 'Tennessee Titans',
  'WAS': 'Washington Commanders'
};

const FantasyDashboard = () => {
  const navigate = useNavigate();
  const location = useLocation();
  
  const [gridApi, setGridApi] = useState(null);
  const [players, setPlayers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [filters, setFilters] = useState({
    season: '2025',
    week: '4',  // Single week selection (for backward compatibility)
    weekStart: null,  // Start of week range
    weekEnd: null,    // End of week range
    position: 'QB',
    team: 'all',
    minSalary: '',
    minSnaps: ''
  });
  
  // New state for enhanced features
  const [isPPR, setIsPPR] = useState(true); // true = full PPR, false = half PPR
  const [selectedPlayer, setSelectedPlayer] = useState(null);
  const [playerDetailOpen, setPlayerDetailOpen] = useState(false);
  const [playerGameHistory, setPlayerGameHistory] = useState([]);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(280); // pixels
  const [isResizing, setIsResizing] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [sortConfig, setSortConfig] = useState({ key: 'fantasy_points', direction: 'desc' });
  const [lastUpdated, setLastUpdated] = useState(null);
  const [favorites, setFavorites] = useState([]);
  const [selectedPlayers, setSelectedPlayers] = useState([]);
  const [activeTab, setActiveTab] = useState(() => {
    // Initialize from URL path
    if (location.pathname === '/trend-tool') return 'trend-tool';
    return 'data-table';
  });
  const [filtersCollapsed, setFiltersCollapsed] = useState(false);
  
  // Trend Tool state
  const [trendFilters, setTrendFilters] = useState({
    team: 'NYG',
    startWeek: 4,
    endWeek: 6,
    season: '2025'
  });
  const [trendData, setTrendData] = useState([]);
  const [columnWidths, setColumnWidths] = useState(() => {
    const saved = localStorage.getItem('trendToolColumnWidths');
    return saved ? JSON.parse(saved) : {};
  });
  const [collapsedColumns, setCollapsedColumns] = useState(() => {
    const saved = localStorage.getItem('trendToolCollapsedColumns');
    return saved ? JSON.parse(saved) : {};
  });
  
  // New states for Trend Tool enhancements
  const [trendFiltersCollapsed, setTrendFiltersCollapsed] = useState(false);
  
  const [showOptimizerFilter, setShowOptimizerFilter] = useState(false);

  useEffect(() => {
    if (activeTab === 'data-table' && location.pathname !== '/data-table') {
      navigate('/data-table', { replace: true });
    } else if (activeTab === 'trend-tool' && location.pathname !== '/trend-tool') {
      navigate('/trend-tool', { replace: true });
    }
  }, [activeTab, navigate, location.pathname]);

  useEffect(() => {
    if (location.pathname === '/trend-tool' && activeTab !== 'trend-tool') {
      setActiveTab('trend-tool');
    } else if (location.pathname === '/data-table' && activeTab !== 'data-table') {
      setActiveTab('data-table');
    } else if (location.pathname === '/' && activeTab !== 'data-table') {
      setActiveTab('data-table');
      navigate('/data-table', { replace: true });
    }
  }, [location.pathname, activeTab, navigate]);

  // Calculate fantasy points based on PPR setting
  const calculateFantasyPoints = (player) => {
    let points = 0;
    
    // Passing
    points += (player.passing_yards || 0) * 0.04;
    points += (player.passing_tds || 0) * 4;
    points += (player.interceptions || 0) * -1;
    
    // Rushing
    points += (player.rushing_yards || 0) * 0.1;
    points += (player.rushing_tds || 0) * 6;
    
    // Receiving
    points += (player.receiving_yards || 0) * 0.1;
    points += (player.receiving_tds || 0) * 6;
    points += (player.receptions || 0) * (isPPR ? 1 : 0.5); // Full PPR vs Half PPR
    
    // Fumbles
    points += (player.fumbles_lost || 0) * -1;
    
    return points.toFixed(1);
  };

  // Get performance color based on value and position
  const getPerformanceColor = (value, type, position) => {
    if (!value || value === 0) return 'text-gray-400';
    
    // Different thresholds based on stat type and position
    const thresholds = {
      fantasy_points: { good: 15, average: 8 },
      snap_percentage: { good: 60, average: 30 },
      passing_yards: { good: 250, average: 150 },
      rushing_yards: { good: 80, average: 40 },
      receiving_yards: { good: 80, average: 40 },
      receptions: { good: 6, average: 3 }
    };
    
    const threshold = thresholds[type];
    if (!threshold) return 'text-gray-700';
    
    if (value >= threshold.good) return 'text-green-600 font-semibold';
    if (value >= threshold.average) return 'text-yellow-600';
    return 'text-red-500';
  };

  // Get position color for badges
  const getPositionColor = (position) => {
    const colors = {
      'QB': 'bg-purple-100 text-purple-800 border-purple-300',
      'RB': 'bg-green-100 text-green-800 border-green-300',
      'WR': 'bg-blue-100 text-blue-800 border-blue-300',
      'TE': 'bg-orange-100 text-orange-800 border-orange-300'
    };
    return colors[position] || 'bg-gray-100 text-gray-800 border-gray-300';
  };

  // Handle sidebar resizing
  const handleMouseDown = (e) => {
    setIsResizing(true);
    e.preventDefault();
  };

  const handleMouseMove = (e) => {
    if (!isResizing) return;
    
    const newWidth = e.clientX;
    if (newWidth >= 200 && newWidth <= 400) {
      setSidebarWidth(newWidth);
    }
  };

  const handleMouseUp = () => {
    setIsResizing(false);
  };

  React.useEffect(() => {
    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      
      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isResizing]);

  // Handle player click to open detail panel
  const handlePlayerClick = async (player) => {
    setSelectedPlayer(player);
    setPlayerDetailOpen(true);
    await fetchPlayerGameHistory(player);
  };

  // Fetch last 5 games for selected player with DK pricing and snaps
  const fetchPlayerGameHistory = async (player) => {
    try {
      const currentWeek = filters.week === 'all' ? 18 : parseInt(filters.week);
      const season = filters.season;
      
      const response = await axios.get(`${API}/players`, {
        params: {
          season: season,
          limit: 50,
          player_name: player.player_name
        }
      });
      
      // Filter and sort to get last 5 games from current week backwards
      const games = response.data
        .filter(game => 
          game.player_name === player.player_name && 
          (filters.week === 'all' || game.week <= currentWeek)
        )
        .sort((a, b) => b.week - a.week)
        .slice(0, 5); // Changed to 5 games
      
      setPlayerGameHistory(games);
    } catch (error) {
      console.error('Error fetching player game history:', error);
      setPlayerGameHistory([]);
    }
  };

  // Column definitions with grouped headers
  const columnDefs = useMemo(() => [
    // Player Info Group (Pinned Left)
    {
      headerName: 'PLAYER INFO',
      headerClass: 'player-info-group-header',
      children: [
        {
          headerName: 'Player',
          field: 'player_name',
          pinned: 'left',
          width: 140,
      cellRenderer: (params) => (
        <div className="flex items-center justify-between py-1 px-2 group">
          <div 
            className="cursor-pointer hover:text-blue-600 transition-colors flex-1"
            onClick={() => handlePlayerClick(params.data)}
          >
            <div className="font-medium text-gray-900 text-sm">{params.value}</div>
          </div>
          <Button
            size="sm"
            variant="ghost"
            className="opacity-0 group-hover:opacity-100 transition-opacity p-1 h-5 w-5"
            onClick={(e) => {
              e.stopPropagation();
              toggleFavorite(params.data.player_id);
            }}
          >
            <Heart 
              className={`h-3 w-3 ${
                favorites.includes(params.data.player_id) 
                  ? 'fill-red-500 text-red-500' 
                  : 'text-gray-400 hover:text-red-500'
              }`} 
            />
          </Button>
        </div>
      )
    },
    {
      headerName: 'Game',
      field: 'opponent',
      pinned: 'left',
      width: 100,
      cellRenderer: (params) => {
        const opponent = params.value;
        const playerTeam = params.data.team;
        const week = params.data.week;
        
        const score = `vs ${opponent}`;
        
        return (
          <div className="py-1 px-2">
            <div className="text-xs font-semibold text-gray-700">
              {score}
            </div>
            <div className="text-xs text-gray-500">
              Week {week}
            </div>
          </div>
        );
      }
    }]
    },
    
    // Basic Stats Group
    {
      headerName: 'BASIC STATS',
      headerClass: 'basic-stats-group-header',
      children: [
        {
          headerName: 'Pos',
          field: 'position',
          width: 50,
          cellRenderer: (params) => (
            <div className="py-1 px-2">
              <span className="text-sm font-medium text-blue-600">{params.value}</span>
            </div>
          )
        },
        {
          headerName: 'DK $',
          field: 'dk_salary',
          width: 70,
          type: 'numericColumn',
          cellRenderer: (params) => {
            const salary = params.value;
            // Only show DK salary for 2025 data
            if (params.data.season !== '2025') {
              return <div className="py-1 px-2 text-sm text-gray-400">-</div>;
            }
            if (salary && salary > 0) {
              return (
                <div className="py-1 px-2">
                  <span className="text-sm font-semibold text-green-700">
                    ${(salary/1000).toFixed(1)}k
                  </span>
                </div>
              );
            }
            return <div className="py-1 px-2 text-sm text-gray-400">-</div>;
          }
        },
        {
          headerName: '# Snaps',
          field: 'snap_percentage',
          width: 70,
          type: 'numericColumn',
          cellRenderer: (params) => (
            <div className="py-1 px-2">
              <span className="text-sm font-medium text-gray-800">
                {params.value && params.value > 0 ? Math.round(params.value) : '-'}
              </span>
            </div>
          )
        },
        {
          headerName: 'FPTS',
          field: 'fantasy_points',
          width: 80,
          type: 'numericColumn',
          valueGetter: (params) => calculateFantasyPoints(params.data),
          cellRenderer: (params) => {
            const points = parseFloat(params.value) || 0;
            const maxPoints = 35; // Max scale for progress bar
            const percentage = Math.min((points / maxPoints) * 100, 100);
            
            // Color coding based on performance
            let barColor = 'bg-red-400';
            let textColor = 'text-red-700';
            if (points >= 20) {
              barColor = 'bg-green-400';
              textColor = 'text-green-700';
            } else if (points >= 15) {
              barColor = 'bg-yellow-400';
              textColor = 'text-yellow-700';
            } else if (points >= 10) {
              barColor = 'bg-orange-400';
              textColor = 'text-orange-700';
            }
            
            return (
              <div className="py-1 px-2 w-full">
                <div className="relative">
                  <div className="w-full bg-gray-200 rounded-full h-2 mb-1">
                    <div 
                      className={`h-2 rounded-full transition-all duration-300 ${barColor}`}
                      style={{ width: `${percentage}%` }}
                    ></div>
                  </div>
                  <div className={`text-xs font-bold ${textColor}`}>
                    {points.toFixed(1)}
                  </div>
                </div>
              </div>
            );
          },
          sort: 'desc'
        }]
    },
    
    // Passing Stats Group
    {
      headerName: 'PASSING',
      headerClass: 'passing-group-header',
      children: [
        {
          headerName: 'Cmp-Att',
          field: 'passing_attempts',
          width: 75,
          type: 'numericColumn',
          cellClass: 'passing-group-cell',
          valueGetter: (params) => {
            const att = params.data.passing_yards > 0 ? Math.ceil(params.data.passing_yards / 8.5) : 0;
            const cmp = Math.ceil(att * 0.65); // Estimate completion rate
            return att > 0 ? `${cmp}-${att}` : '-';
          },
          cellRenderer: (params) => (
            <div className="py-1 px-2">
              <span className="text-sm">{params.value}</span>
            </div>
          )
        },
        {
          headerName: 'Yds',
          field: 'passing_yards',
          width: 60,
          type: 'numericColumn',
          cellClass: 'passing-group-cell',
          cellRenderer: (params) => (
            <div className="py-1 px-2">
              <span className="text-sm font-medium">{params.value || '-'}</span>
            </div>
          )
        },
        {
          headerName: 'TD',
          field: 'passing_tds', 
          width: 50,
          type: 'numericColumn',
          cellClass: 'passing-group-cell',
          cellRenderer: (params) => (
            <div className="py-1 px-2">
              <span className="text-sm font-medium">{params.value || '-'}</span>
            </div>
          )
        },
        {
          headerName: 'Int.',
          field: 'interceptions',
          width: 50,
          type: 'numericColumn', 
          cellClass: 'passing-group-cell',
          cellRenderer: (params) => (
            <div className="py-1 px-2">
              <span className="text-sm">{params.value || '-'}</span>
            </div>
          )
        }]
    },
    // Rushing Stats Group
    {
      headerName: 'RUSHING',
      headerClass: 'rushing-group-header',
      children: [
        {
          headerName: 'Att',
          field: 'rushing_attempts',
          width: 50,
          type: 'numericColumn',
          cellClass: 'rushing-group-cell',
          valueGetter: (params) => params.data.rushing_yards > 0 ? Math.ceil(params.data.rushing_yards / 4.5) : 0,
          cellRenderer: (params) => (
            <div className="py-1 px-2">
              <span className="text-sm">{params.value || '-'}</span>
            </div>
          )
        },
        {
          headerName: 'Yds',
          field: 'rushing_yards',
          width: 60,
          type: 'numericColumn',
          cellClass: 'rushing-group-cell',
          cellRenderer: (params) => (
            <div className="py-1 px-2">
              <span className="text-sm font-medium">{params.value || '-'}</span>
            </div>
          )
        },
        {
          headerName: 'TD',
          field: 'rushing_tds',
          width: 50,
          type: 'numericColumn',
          cellClass: 'rushing-group-cell',
          cellRenderer: (params) => (
            <div className="py-1 px-2">
              <span className="text-sm font-medium">{params.value || '-'}</span>
            </div>
          )
        }]
    },
    // Receiving Stats Group
    {
      headerName: 'RECEIVING',
      headerClass: 'receiving-group-header',
      children: [
        {
          headerName: 'Tgt',
          field: 'targets',
          width: 50,
          type: 'numericColumn',
          cellClass: 'receiving-group-cell',
          cellRenderer: (params) => (
            <div className="py-1 px-2">
              <span className="text-sm">{params.value || '-'}</span>
            </div>
          )
        },
        {
          headerName: 'Rec',
          field: 'receptions',
          width: 50,
          type: 'numericColumn',
          cellClass: 'receiving-group-cell',
          cellRenderer: (params) => (
            <div className="py-1 px-2">
              <span className="text-sm font-medium">{params.value || '-'}</span>
            </div>
          )
        },
        {
          headerName: 'Yds',
          field: 'receiving_yards',
          width: 60,
          type: 'numericColumn',
          cellClass: 'receiving-group-cell',
          cellRenderer: (params) => (
            <div className="py-1 px-2">
              <span className="text-sm font-medium">{params.value || '-'}</span>
            </div>
          )
        },
        {
          headerName: 'TD',
          field: 'receiving_tds',
          width: 50,
          type: 'numericColumn',
          cellClass: 'receiving-group-cell',
          cellRenderer: (params) => (
            <div className="py-1 px-2">
              <span className="text-sm font-medium">{params.value || '-'}</span>
            </div>
          )
        }]
    }
  ], [isPPR, calculateFantasyPoints, getPerformanceColor, handlePlayerClick, favorites]);

  // Default column configuration with tighter spacing - remove filter triangles
  const defaultColDef = useMemo(() => ({
    sortable: true,
    filter: false, // Remove filter triangles
    resizable: true,
    minWidth: 40,
    cellStyle: { padding: '4px 6px' },
    suppressMenu: true // Remove column menu
  }), []);

  // Grid options for clean layout
  const gridOptions = useMemo(() => ({
    theme: 'legacy',
    rowHeight: 32,
    headerHeight: 36,
    rowSelection: 'none',
    pagination: true,
    paginationPageSize: 50,
    animateRows: false
  }), []);


  // Fetch players data
  const fetchPlayers = async () => {
    try {
      setLoading(true);
      
      // Build params based on whether we're using week range or single week
      const params = {
        season: filters.season,
        position: filters.position !== 'all' ? filters.position : undefined,
        team: filters.team !== 'all' ? filters.team : undefined,
        limit: 1000
      };
      
      // Add week parameters based on selection
      if (filters.weekStart && filters.weekEnd) {
        // Week range mode
        params.week_start = filters.weekStart;
        params.week_end = filters.weekEnd;
      } else if (filters.week && filters.week !== 'all') {
        // Single week mode
        params.week = filters.week;
      }
      // If week is 'all' or not set, don't add any week parameter
      
      const response = await axios.get(`${API}/players`, { params });
      
      const playersData = response.data || [];
      setPlayers(playersData);
      setLastUpdated(new Date());
    } catch (error) {
      console.error('Error fetching players:', error);
      setPlayers([]);
    } finally {
      setLoading(false);
    }
  };

  // Filter and search functionality
  const filteredPlayers = useMemo(() => {
    let filtered = players;
    
    // Apply search filter
    if (searchTerm) {
      filtered = filtered.filter(player => 
        player.player_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        player.team.toLowerCase().includes(searchTerm.toLowerCase()) ||
        player.position.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }
    
    return filtered;
  }, [players, searchTerm]);

  // Get active filters for display
  const getActiveFilters = () => {
    const active = [];
    if (filters.season !== '2024') active.push({ key: 'season', value: filters.season, label: `Season: ${filters.season}` });
    if (filters.week !== 'all') active.push({ key: 'week', value: filters.week, label: `Week: ${filters.week}` });
    if (filters.position !== 'all') active.push({ key: 'position', value: filters.position, label: `Position: ${filters.position}` });
    if (filters.team !== 'all') active.push({ key: 'team', value: filters.team, label: `Team: ${filters.team}` });
    if (filters.minSalary) active.push({ key: 'minSalary', value: filters.minSalary, label: `Min Salary: $${filters.minSalary}` });
    if (filters.minSnaps) active.push({ key: 'minSnaps', value: filters.minSnaps, label: `Min Snaps: ${filters.minSnaps}` });
    if (searchTerm) active.push({ key: 'search', value: searchTerm, label: `Search: "${searchTerm}"` });
    return active;
  };

  // Clear specific filter
  const clearFilter = (key) => {
    if (key === 'search') {
      setSearchTerm('');
    } else {
      const defaultValues = {
        season: '2024',
        week: 'all', 
        position: 'all',
        team: 'all',
        minSalary: '',
        minSnaps: ''
      };
      handleFilterChange(key, defaultValues[key] || '');
    }
  };

  // Toggle favorite player
  const toggleFavorite = (playerId) => {
    setFavorites(prev => {
      const newFavorites = prev.includes(playerId) 
        ? prev.filter(id => id !== playerId)
        : [...prev, playerId];
      
      toast.success(
        newFavorites.includes(playerId) 
          ? 'Player added to favorites!' 
          : 'Player removed from favorites!'
      );
      
      return newFavorites;
    });
  };

  // Keyboard shortcuts
  const handleKeyboardShortcuts = useCallback((event) => {
    // Cmd/Ctrl + K for search focus
    if ((event.metaKey || event.ctrlKey) && event.key === 'k') {
      event.preventDefault();
      document.querySelector('input[placeholder*="Search"]')?.focus();
    }
    
    // Cmd/Ctrl + R for refresh (prevent browser refresh, use our refresh)
    if ((event.metaKey || event.ctrlKey) && event.key === 'r') {
      event.preventDefault();
      refreshData();
    }
    
    // Cmd/Ctrl + E for export
    if ((event.metaKey || event.ctrlKey) && event.key === 'e') {
      event.preventDefault();
      exportData();
    }
    
    // Escape to clear search
    if (event.key === 'Escape') {
      setSearchTerm('');
      setPlayerDetailOpen(false);
    }
  }, []);

  // Export data functionality
  const exportData = useCallback(() => {
    const csvData = filteredPlayers.map(player => ({
      Player: player.player_name,
      Team: player.team,
      Position: player.position,
      Fantasy_Points: calculateFantasyPoints(player),
      Snaps: player.snap_percentage,
      Rushing_Yards: player.rushing_yards || 0,
      Receiving_Yards: player.receiving_yards || 0,
      Passing_Yards: player.passing_yards || 0,
      DK_Salary: player.dk_salary || 0
    }));
    
    const csvString = [
      Object.keys(csvData[0]).join(','),
      ...csvData.map(row => Object.values(row).join(','))
    ].join('\n');
    
    const blob = new Blob([csvString], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `nfl-fantasy-data-${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
    window.URL.revokeObjectURL(url);
    
    toast.success('Data exported successfully!');
  }, [filteredPlayers, calculateFantasyPoints]);

  // Add keyboard event listener
  useEffect(() => {
    document.addEventListener('keydown', handleKeyboardShortcuts);
    return () => document.removeEventListener('keydown', handleKeyboardShortcuts);
  }, [handleKeyboardShortcuts]);


  // Refresh data from NFL sources
  const refreshData = async () => {
    try {
      setRefreshing(true);
      
      // Fetch player data
      await fetchPlayersWithFilters();
      
      toast.success('Data refreshed successfully', { duration: 2000 });
    } catch (error) {
      console.error('Error refreshing data:', error);
      toast.error('Failed to refresh data', { duration: 3000 });
    } finally {
      setRefreshing(false);
    }
  };

  // Initial data load
  useEffect(() => {
    fetchPlayersWithFilters();
  }, []);

  // PPR change handler
  useEffect(() => {
    if (players.length > 0) {
      // Re-trigger grid update when PPR changes since fantasy points are calculated
      setLastUpdated(new Date());
    }
  }, [isPPR]);

  // Refetch when filters change
  useEffect(() => {
    fetchPlayersWithFilters();
  }, [filters]);

  // Fetch trend data
  const fetchTrendData = async () => {
    try {
      setLoading(true);
      const promises = [];
      
      // Fetch data for each week in the range
      for (let week = trendFilters.startWeek; week <= trendFilters.endWeek; week++) {
        const response = axios.get(`${API}/players`, {
          params: {
            season: trendFilters.season,
            week: week,
            team: trendFilters.team,
            limit: 100
          }
        });
        promises.push(response);
      }
      
      const results = await Promise.all(promises);
      
      // Process and combine the data
      const processedData = [];
      const playerMap = new Map();
      
      results.forEach((response, index) => {
        const weekNum = trendFilters.startWeek + index;
        const weekData = response.data || [];
        
        weekData.forEach(player => {
          const key = `${player.player_name}-${player.position}`;
          if (!playerMap.has(key)) {
            playerMap.set(key, {
              player_name: player.player_name,
              position: player.position,
              team: player.team,
              weeks: {}
            });
          }
          playerMap.get(key).weeks[weekNum] = {
            ...player,
            fantasy_points: parseFloat(calculateFantasyPoints(player)) || 0
          };
        });
      });
      
      // Convert to array and sort by position and name
      const trendArray = Array.from(playerMap.values()).sort((a, b) => {
        if (a.position !== b.position) {
          const posOrder = ['QB', 'RB', 'WR', 'TE'];
          return posOrder.indexOf(a.position) - posOrder.indexOf(b.position);
        }
        return a.player_name.localeCompare(b.player_name);
      });
      
      setTrendData(trendArray);
      
    } catch (error) {
      console.error('Error fetching trend data:', error);
      toast.error('Error loading trend data');
    } finally {
      setLoading(false);
    }
  };

  // Fetch trend data when filters change
  useEffect(() => {
    if (activeTab === 'trend-tool') {
      fetchTrendData();
    }
  }, [trendFilters, activeTab]);

  // Column resize handler
  const handleColumnResize = (e, columnKey) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = parseInt(columnWidths[columnKey] || '50px');
    
    const handleMouseMove = (e) => {
      const newWidth = Math.max(25, startWidth + (e.clientX - startX));
      const newWidths = { ...columnWidths, [columnKey]: `${newWidth}px` };
      setColumnWidths(newWidths);
      localStorage.setItem('trendToolColumnWidths', JSON.stringify(newWidths));
    };
    
    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
    
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  const onGridReady = (params) => {
    setGridApi(params.api);
    params.api.sizeColumnsToFit();
  };

  // Handle filter changes with auto-apply
  const handleFilterChange = (filterType, value) => {
    const newFilters = { ...filters, [filterType]: value };
    setFilters(newFilters);
    
    // Auto-apply filters after a short delay
    setTimeout(() => {
      fetchPlayersWithFilters(newFilters);
    }, 300);
  };

  // Separate function for fetching with specific filters
  const fetchPlayersWithFilters = async (filterParams = filters) => {
    try {
      setLoading(true);
      
      // Prepare clean parameters for backend
      const cleanParams = {
        season: filterParams.season,
        limit: 1000
      };
      
      // Add week parameters based on selection mode
      if (filterParams.weekStart && filterParams.weekEnd) {
        // Week range mode
        cleanParams.week_start = filterParams.weekStart;
        cleanParams.week_end = filterParams.weekEnd;
      } else if (filterParams.week && filterParams.week !== 'all') {
        // Single week mode
        cleanParams.week = filterParams.week;
      }
      // If week is 'all' or not set, don't add any week parameter
      
      // Add position if not 'all'
      if (filterParams.position && filterParams.position !== 'all') {
        cleanParams.position = filterParams.position;
      }
      
      // Add team if not 'all' 
      if (filterParams.team && filterParams.team !== 'all') {
        cleanParams.team = filterParams.team;
      }
      
      // Add salary filter if specified
      if (filterParams.minSalary) {
        cleanParams.minSalary = filterParams.minSalary;
      }
      
      // Add snaps filter if specified
      if (filterParams.minSnaps) {
        cleanParams.minSnaps = filterParams.minSnaps;
      }
      
      console.log('Fetching with params:', cleanParams);
      
      const response = await axios.get(`${API}/players`, { 
        params: cleanParams
      });
      
      const playersData = response.data || [];
      setPlayers(playersData);
      setLastUpdated(new Date());
      
      if (playersData.length === 0) {
        toast.info(`No players found for selected filters`, { duration: 2000 });
      } else {
        toast.success(`Loaded ${playersData.length} players`, { duration: 1500 });
      }
    } catch (error) {
      console.error('Error fetching players:', error);
      setPlayers([]);
      toast.error('Error loading player data', { duration: 3000 });
    } finally {
      setLoading(false);
    }
  };

  const PlayerTypeButton = ({ type, label, active, onClick }) => (
    <Button
      variant={active ? "default" : "outline"}
      size="sm"
      onClick={() => onClick(type)}
      className={`text-xs px-3 py-1.5 h-8 ${
        active ? 'bg-blue-600 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'
      }`}
      data-testid={`player-type-${type}`}
    >
      {label}
    </Button>
  );

  return (
    <div className="flex h-screen bg-gray-50">
      <Toaster position="top-right" />
      
      {/* MenuWise Sidebar - New */}
      <div className="w-72 flex-shrink-0">
        <MenuWiseSidebar 
          activeRoute={location.pathname}
          onNavigate={(path) => navigate(path)}
        />
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Professional Header with Texture */}
        <div className="bg-gradient-to-r from-slate-900 via-blue-900 to-indigo-900 shadow-2xl border-b-4 border-blue-500">
        <div className="relative overflow-hidden">
          {/* Texture overlay */}
          <div className="absolute inset-0 bg-black/20 bg-[radial-gradient(circle_at_20%_80%,_rgba(120,_119,_198,_0.3),_transparent_50%)]"></div>
          <div className="absolute inset-0 bg-[linear-gradient(45deg,_transparent_25%,_rgba(255,255,255,0.02)_25%,_rgba(255,255,255,0.02)_50%,_transparent_50%,_transparent_75%,_rgba(255,255,255,0.02)_75%)] bg-[length:4px_4px]"></div>
          
          <div className="relative max-w-full mx-auto px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-4">
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-blue-500/20 rounded-lg shadow-lg border border-blue-400/30">
                    <img 
                      src="https://static.vecteezy.com/system/resources/thumbnails/053/257/088/small/fantasy-football-logo-white-line-stars-and-shield-vector.jpg" 
                      alt="Fantasy Football Logo" 
                      className="h-8 w-8 object-contain filter brightness-0 invert"
                    />
                  </div>
                  <div>
                    <h1 className="text-2xl font-bold text-white tracking-tight">NFL DK DASHBOARD</h1>
                    <p className="text-blue-200 text-sm">DraftKings Analytics & Player Stats</p>
                  </div>
                </div>
                <div className="hidden md:flex items-center space-x-2">
                  <Badge className="bg-blue-500/20 text-blue-100 border-blue-400 text-xs px-3 py-1">
                    DraftKings PPR
                  </Badge>
                  <Badge className="bg-green-500/20 text-green-100 border-green-400 text-xs px-3 py-1">
                    Live Data
                  </Badge>
                  <Badge 
                    className="bg-purple-500/20 text-purple-100 border-purple-400 text-xs px-3 py-1 cursor-pointer hover:bg-purple-500/30 transition-colors"
                    onClick={() => setShowOptimizerFilter(!showOptimizerFilter)}
                  >
                    Optimizer {showOptimizerFilter ? '✓' : '(Beta)'}
                  </Badge>
                </div>
              </div>
              
              <div className="flex items-center space-x-2">
                <Button 
                  size="sm" 
                  className="bg-blue-600 hover:bg-blue-700 text-white border-0 shadow-lg text-xs h-9"
                  onClick={() => {
                    refreshData();
                    toast.success('Refreshing data...', { duration: 1500 });
                  }}
                  disabled={refreshing}
                >
                  <RefreshCw className={`h-3 w-3 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
                  {refreshing ? 'Syncing...' : 'Sync Data (⌘R)'}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>

        {/* Optimizer Filter Component */}
        <OptimizerFilter
          isVisible={showOptimizerFilter}
          onClose={() => setShowOptimizerFilter(false)}
          currentPosition={filters.position}
          currentWeek={filters.week}
          onPositionChange={(position) => setFilters(prev => ({ ...prev, position }))}
          onWeekChange={(week) => setFilters(prev => ({ ...prev, week }))}
        />

        {/* Content Area - Full Width */}
        <div className="flex-1 overflow-auto">
        {/* Tab Content */}
        {activeTab === 'data-table' && (
          <div className="h-full p-6 flex gap-4 overflow-hidden">
              {/* Main Data Grid */}
              <Card 
                className="shadow-lg border-0 bg-white transition-all duration-300 ease-in-out" 
                style={{ 
                  width: playerDetailOpen ? '70%' : '100%'
                }}
              >
                <CardHeader className="pb-2 px-4 py-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-4">
                      {/* Quick Stats */}
                      <div className="flex items-center space-x-3">
                        <Badge variant="outline" className="text-xs px-2 py-1">
                          <Eye className="h-3 w-3 mr-1" />
                          {filteredPlayers.length.toLocaleString()} players
                        </Badge>
                        {favorites.length > 0 && (
                          <Badge variant="outline" className="text-xs px-2 py-1 bg-red-50 text-red-700 border-red-200">
                            <Heart className="h-3 w-3 mr-1" />
                            {favorites.length} favorites
                          </Badge>
                        )}
                        {lastUpdated && (
                          <Badge variant="outline" className="text-xs px-2 py-1 bg-green-50 text-green-700 border-green-200">
                            <Zap className="h-3 w-3 mr-1" />
                            Updated {new Date(lastUpdated).toLocaleTimeString()}
                          </Badge>
                        )}
                      </div>
                      
                      {/* Search Input */}
                      <div className="relative">
                        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                        <Input
                          type="text"
                          placeholder="Search players, teams, positions... (⌘K)"
                          value={searchTerm}
                          onChange={(e) => setSearchTerm(e.target.value)}
                          className="pl-10 pr-4 py-2 w-80 text-sm border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        />
                        {searchTerm && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="absolute right-2 top-1/2 transform -translate-y-1/2 h-6 w-6 p-0"
                            onClick={() => setSearchTerm('')}
                          >
                            ×
                          </Button>
                        )}
                      </div>
                    </div>
                    
                    {/* Action Buttons */}
                    <div className="flex items-center space-x-2">
                      <Button 
                        size="sm" 
                        className="bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 text-white border-0 shadow-lg text-xs h-8 px-3"
                      >
                        <Star className="h-3 w-3 mr-1" />
                        Favorites
                      </Button>
                      <Button 
                        size="sm" 
                        className="bg-gradient-to-r from-green-500 to-emerald-600 hover:from-green-600 hover:to-emerald-700 text-white border-0 shadow-lg text-xs h-8 px-3"
                        onClick={exportData}
                      >
                        <Download className="h-3 w-3 mr-1" />
                        Export CSV (⌘E)
                      </Button>
                      
                      {/* Keyboard Shortcuts Help */}
                      <Button 
                        size="sm" 
                        variant="outline"
                        className="text-xs h-8 px-3"
                        onClick={() => toast.info(
                          '⌘K: Focus search • ⌘R: Refresh data • ⌘E: Export • Escape: Clear search',
                          { duration: 4000 }
                        )}
                      >
                        <Settings className="h-3 w-3 mr-1" />
                        Shortcuts
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                
                <CardContent className="p-0">
                  {/* Clean Professional Grid */}
                  {loading ? (
                    <div className="p-6">
                      <div className="animate-pulse space-y-4">
                        {/* Header skeleton */}
                        <div className="flex space-x-4">
                          <div className="h-4 bg-gray-200 rounded w-20"></div>
                          <div className="h-4 bg-gray-200 rounded w-16"></div>
                          <div className="h-4 bg-gray-200 rounded w-12"></div>
                          <div className="h-4 bg-gray-200 rounded w-24"></div>
                          <div className="h-4 bg-gray-200 rounded w-16"></div>
                          <div className="h-4 bg-gray-200 rounded w-20"></div>
                        </div>
                        {/* Data skeleton */}
                        {[...Array(15)].map((_, i) => (
                          <div key={i} className="flex space-x-4">
                            <div className="h-3 bg-gray-200 rounded w-32"></div>
                            <div className="h-3 bg-gray-200 rounded w-12"></div>
                            <div className="h-3 bg-gray-200 rounded w-8"></div>
                            <div className="h-3 bg-gray-200 rounded w-16"></div>
                            <div className="h-3 bg-gray-200 rounded w-12"></div>
                            <div className="h-3 bg-gray-200 rounded w-16"></div>
                            <div className="h-3 bg-gray-200 rounded w-12"></div>
                            <div className="h-3 bg-gray-200 rounded w-16"></div>
                            <div className="h-3 bg-gray-200 rounded w-12"></div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div 
                      className="ag-theme-alpine professional-grid compact-data-grid"
                      style={{ 
                        height: '600px', 
                        width: '100%'
                      }}
                    >
                      <AgGridReact
                        columnDefs={columnDefs}
                        rowData={filteredPlayers}
                        defaultColDef={defaultColDef}
                        gridOptions={gridOptions}
                        onGridReady={onGridReady}
                        loading={loading}
                        data-testid="player-stats-grid"
                      />
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Player Detail Panel */}
              {playerDetailOpen && selectedPlayer && (
                <Card 
                  className="w-[38%] shadow-2xl border-l-4 border-blue-500 flex flex-col"
                  style={{ minWidth: '420px', maxWidth: '640px', height: '100%' }}
                >
                  {/* Header - Sticky */}
                  <CardHeader className="pb-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white px-4 py-4 sticky top-0 z-30 shadow-md">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-4">
                        <div>
                          <CardTitle className="text-xl font-bold">
                            {selectedPlayer?.player_name}
                          </CardTitle>
                          <CardDescription className="text-blue-100 text-sm mt-1">
                            {selectedPlayer?.team} • {selectedPlayer?.position} • Season {filters.season}
                          </CardDescription>
                        </div>
                        <Badge className="text-sm px-3 py-1.5 font-bold bg-white text-blue-600 border-0 shadow-lg">
                          {selectedPlayer?.position}
                        </Badge>
                      </div>
                      <Button 
                        size="sm" 
                        variant="ghost" 
                        className="text-white hover:bg-white/20 h-8 w-8 p-0 rounded-full"
                        onClick={() => setPlayerDetailOpen(false)}
                      >
                        ×
                      </Button>
                    </div>
                    
                    {/* Rankings Bar */}
                    <div className="mt-3 bg-white/10 backdrop-blur-sm rounded-lg px-4 py-2">
                      <div className="text-xs text-blue-100 mb-1 font-semibold">2025 RANKINGS (PPR)</div>
                      <div className="grid grid-cols-3 gap-3 text-center">
                        <div>
                          <div className="text-xs text-blue-200">Preseason</div>
                          <div className="text-sm font-bold text-white">{selectedPlayer?.position}??</div>
                        </div>
                        <div>
                          <div className="text-xs text-blue-200">Current</div>
                          <div className="text-sm font-bold text-white">{selectedPlayer?.position}??</div>
                        </div>
                        <div>
                          <div className="text-xs text-blue-200">Week {filters.week}</div>
                          <div className="text-sm font-bold text-white">{selectedPlayer?.position}??</div>
                        </div>
                      </div>
                    </div>
                  </CardHeader>
                  
                  <CardContent className="p-0 overflow-y-auto flex-1" style={{ height: 'calc(100vh - 200px)' }}>
                    {/* Game-by-Game Stats Table */}
                    <div className="p-4">
                      <h4 className="text-sm font-bold mb-3 text-gray-700 uppercase tracking-wide">Game-by-Game Statistics</h4>
                      <div className="overflow-x-auto border rounded-lg">
                        <table className="w-full text-xs">
                          <thead className="bg-gradient-to-r from-gray-100 to-gray-50 sticky top-0 z-20">
                            <tr>
                              <th className="px-2 py-2 text-left font-bold text-gray-700 border-b border-r">Week</th>
                              <th className="px-2 py-2 text-left font-bold text-gray-700 border-b border-r">Opp</th>
                              <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">Result</th>
                              <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r bg-indigo-50">Snaps</th>
                              <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r bg-green-50">DK $</th>
                              
                              {selectedPlayer?.position === 'QB' && (
                                <>
                                  <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">Cmp</th>
                                  <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">Att</th>
                                  <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">Yds</th>
                                  <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">TD</th>
                                  <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">INT</th>
                                  <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">Rush Yds</th>
                                </>
                              )}
                              
                              {selectedPlayer?.position === 'RB' && (
                                <>
                                  <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">Att</th>
                                  <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">Rush Yds</th>
                                  <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">Rush TD</th>
                                  <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">Rec</th>
                                  <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">Rec Yds</th>
                                  <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">Rec TD</th>
                                </>
                              )}
                              
                              {(selectedPlayer?.position === 'WR' || selectedPlayer?.position === 'TE') && (
                                <>
                                  <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">Tgts</th>
                                  <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">Rec</th>
                                  <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">Rec Yds</th>
                                  <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">Rec TD</th>
                                  <th className="px-2 py-2 text-center font-bold text-gray-700 border-b border-r">Lng</th>
                                </>
                              )}
                              
                              <th className="px-2 py-2 text-center font-bold text-white border-b bg-blue-600">FPTS</th>
                            </tr>
                          </thead>
                          <tbody>
                            {playerGameHistory.length > 0 ? (
                              playerGameHistory.map((game, index) => (
                                <tr key={index} className="hover:bg-blue-50/50 transition-colors border-b">
                                  <td className="px-2 py-2 text-left font-semibold text-gray-900 border-r">W{game.week}</td>
                                  <td className="px-2 py-2 text-left text-gray-700 border-r">{game.opponent || 'OPP'}</td>
                                  <td className="px-2 py-2 text-center text-xs text-gray-600 border-r">-</td>
                                  <td className="px-2 py-2 text-center text-gray-900 border-r bg-indigo-50/50">
                                    <div className="font-semibold">{game.snap_count || game.snap_percentage || '-'}</div>
                                    {game.snap_percentage && <div className="text-[10px] text-gray-500">({game.snap_percentage}%)</div>}
                                  </td>
                                  <td className="px-2 py-2 text-center font-semibold text-green-700 border-r bg-green-50/50">
                                    {game.dk_salary ? `$${(game.dk_salary / 1000).toFixed(1)}k` : '-'}
                                  </td>
                                  
                                  {selectedPlayer?.position === 'QB' && (
                                    <>
                                      <td className="px-2 py-2 text-center text-gray-900 border-r">{Math.ceil((game.passing_yards || 0) / 8.5 * 0.65) || '-'}</td>
                                      <td className="px-2 py-2 text-center text-gray-900 border-r">{Math.ceil((game.passing_yards || 0) / 8.5) || '-'}</td>
                                      <td className="px-2 py-2 text-center text-gray-900 border-r font-medium">{game.passing_yards || '-'}</td>
                                      <td className="px-2 py-2 text-center text-green-700 border-r font-semibold">{game.passing_tds || '-'}</td>
                                      <td className="px-2 py-2 text-center text-red-600 border-r font-semibold">{game.interceptions || '-'}</td>
                                      <td className="px-2 py-2 text-center text-gray-900 border-r">{game.rushing_yards || '-'}</td>
                                    </>
                                  )}
                                  
                                  {selectedPlayer?.position === 'RB' && (
                                    <>
                                      <td className="px-2 py-2 text-center text-gray-900 border-r">{Math.ceil((game.rushing_yards || 0) / 4.5) || '-'}</td>
                                      <td className="px-2 py-2 text-center text-gray-900 border-r font-medium">{game.rushing_yards || '-'}</td>
                                      <td className="px-2 py-2 text-center text-green-700 border-r font-semibold">{game.rushing_tds || '-'}</td>
                                      <td className="px-2 py-2 text-center text-gray-900 border-r">{game.receptions || '-'}</td>
                                      <td className="px-2 py-2 text-center text-gray-900 border-r">{game.receiving_yards || '-'}</td>
                                      <td className="px-2 py-2 text-center text-green-700 border-r font-semibold">{game.receiving_tds || '-'}</td>
                                    </>
                                  )}
                                  
                                  {(selectedPlayer?.position === 'WR' || selectedPlayer?.position === 'TE') && (
                                    <>
                                      <td className="px-2 py-2 text-center text-gray-700 border-r">{game.targets || '-'}</td>
                                      <td className="px-2 py-2 text-center text-gray-900 border-r font-medium">{game.receptions || '-'}</td>
                                      <td className="px-2 py-2 text-center text-gray-900 border-r font-medium">{game.receiving_yards || '-'}</td>
                                      <td className="px-2 py-2 text-center text-green-700 border-r font-semibold">{game.receiving_tds || '-'}</td>
                                      <td className="px-2 py-2 text-center text-gray-600 border-r text-xs">-</td>
                                    </>
                                  )}
                                  
                                  <td className="px-2 py-2 text-center font-bold text-blue-600 bg-blue-50">
                                    {calculateFantasyPoints(game).toFixed(1)}
                                  </td>
                                </tr>
                              ))
                            ) : (
                              <tr>
                                <td colSpan="15" className="text-center py-8 text-gray-500">
                                  <div className="text-sm">Loading game history...</div>
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        )}
        
        {/* Trend Tool Tab Content */}
        {activeTab === 'trend-tool' && (
          <div className="p-6 h-full flex flex-col">
            {/* Trend Tool Filters - Collapsible */}
            <div className="mb-4">
              <Card className="shadow-lg border-2 border-blue-200">
                {/* Filter Header with Collapse Button */}
                <div 
                  className="flex items-center justify-between p-4 cursor-pointer bg-blue-50 hover:bg-blue-100 transition-colors border-b-2 border-blue-300"
                  onClick={() => setTrendFiltersCollapsed(!trendFiltersCollapsed)}
                >
                  <div className="flex items-center space-x-3">
                    <Filter className="h-5 w-5 text-blue-700" />
                    <h2 className="text-md font-bold text-gray-900">
                      Filters: {trendFilters.team} | Weeks {trendFilters.startWeek}-{trendFilters.endWeek} | {trendFilters.season}
                    </h2>
                    <Badge className="bg-blue-200 text-blue-900 font-semibold">
                      {trendData.length} Players
                    </Badge>
                  </div>
                  <div className="flex items-center space-x-4">
                    {/* View Mode Toggle */}
                    <div className="flex items-center space-x-2 mr-4">
                      <span className="text-xs text-gray-700 font-bold">View:</span>
                      <div className="flex border-2 border-gray-400 rounded-md overflow-hidden shadow-sm">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setTrendViewMode('summary');
                          }}
                          className={`px-3 py-1 text-xs font-bold transition-colors ${
                            trendViewMode === 'summary'
                              ? 'bg-blue-600 text-white'
                              : 'bg-white text-gray-700 hover:bg-gray-100'
                          }`}
                        >
                          Summary
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setTrendViewMode('full');
                          }}
                          className={`px-3 py-1 text-xs font-bold transition-colors border-l-2 border-gray-400 ${
                            trendViewMode === 'full'
                              ? 'bg-blue-600 text-white'
                              : 'bg-white text-gray-700 hover:bg-gray-100'
                          }`}
                        >
                          Full Detail
                        </button>
                      </div>
                    </div>
                    <button className="text-gray-700 hover:text-gray-900 transition-colors font-bold">
                      {trendFiltersCollapsed ? '▼' : '▲'}
                    </button>
                  </div>
                </div>
                
                {/* Filter Content - Collapsible */}
                {!trendFiltersCollapsed && (
                  <div className="p-4 bg-blue-50 border-t border-blue-200">
                    <div className="flex items-center space-x-6">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Team</label>
                        <Select 
                          value={trendFilters.team} 
                          onValueChange={(value) => setTrendFilters(prev => ({...prev, team: value}))}
                        >
                          <SelectTrigger className="w-24">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {Object.entries(NFL_TEAMS).map(([abbr, name]) => (
                              <SelectItem key={abbr} value={abbr}>{abbr}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Week Range</label>
                        <div className="flex items-center space-x-2">
                          <Select 
                            value={trendFilters.startWeek.toString()} 
                            onValueChange={(value) => setTrendFilters(prev => ({...prev, startWeek: parseInt(value)}))}
                          >
                            <SelectTrigger className="w-16">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {Array.from({length: 18}, (_, i) => (
                                <SelectItem key={i + 1} value={(i + 1).toString()}>{i + 1}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <span className="text-sm text-gray-500">to</span>
                          <Select 
                            value={trendFilters.endWeek.toString()} 
                            onValueChange={(value) => setTrendFilters(prev => ({...prev, endWeek: parseInt(value)}))}
                          >
                            <SelectTrigger className="w-16">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {Array.from({length: 18}, (_, i) => (
                                <SelectItem key={i + 1} value={(i + 1).toString()}>{i + 1}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                      
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Season</label>
                        <Select 
                          value={trendFilters.season} 
                          onValueChange={(value) => setTrendFilters(prev => ({...prev, season: value}))}
                        >
                          <SelectTrigger className="w-20">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="2024">2024</SelectItem>
                            <SelectItem value="2025">2025</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      
                      <div className="flex-1"></div>
                      
                      <div className="text-xs text-gray-500">
                        <div className="bg-blue-50 px-3 py-2 rounded border border-blue-200">
                          <div className="font-medium text-blue-900">💡 Week-to-Week Comparison</div>
                          <div className="text-blue-700 mt-1">Compare player performance across selected weeks</div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </Card>
            </div>

            {/* Trend Data Table */}
            <Card className="flex-1 overflow-hidden">
              <CardContent className="p-0 h-full">
                {loading ? (
                  <div className="p-8 text-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
                    <p>Loading trend data...</p>
                  </div>
                ) : (
                  <div className="h-full overflow-hidden bg-white">
                    <div className="h-full overflow-x-auto overflow-y-auto">
                      <table className="min-w-full border-collapse text-xs font-sans bg-white" style={{tableLayout: 'fixed'}}>
                        <thead className="sticky top-0 z-20">
                          {/* Row 1: Week Headers */}
                          <tr className="bg-gray-700">
                            <th rowSpan="3" className="sticky left-0 bg-blue-600 text-white font-black text-center w-12 z-30 shadow-lg border-r-4 border-gray-900">
                              <div className="py-2 text-xs">Pos</div>
                            </th>
                            <th rowSpan="3" className="sticky left-12 bg-gray-100 text-gray-900 font-black text-left w-32 z-30 shadow-lg border-r-4 border-gray-900 pl-2">
                              <div className="py-2 text-xs">Player</div>
                            </th>
                            {Array.from({length: trendFilters.endWeek - trendFilters.startWeek + 1}, (_, i) => {
                              const week = trendFilters.startWeek + i;
                              const gameResults = {
                                // NYG
                                'NYG-1': { opponent: 'vs MIN', result: 'L', score: '6-28' },
                                'NYG-2': { opponent: '@WAS', result: 'W', score: '21-18' }, 
                                'NYG-3': { opponent: 'vs CLE', result: 'W', score: '21-15' },
                                'NYG-4': { opponent: 'vs DAL', result: 'L', score: '15-20' },
                                'NYG-5': { opponent: '@SEA', result: 'L', score: '17-29' },
                                'NYG-6': { opponent: 'vs CIN', result: 'W', score: '17-7' },
                                'NYG-7': { opponent: '@PHI', result: 'TBD', score: '' },
                                // DAL
                                'DAL-1': { opponent: '@CLE', result: 'W', score: '33-17' },
                                'DAL-2': { opponent: 'vs NO', result: 'W', score: '44-19' },
                                'DAL-3': { opponent: '@BAL', result: 'L', score: '25-28' },
                                'DAL-4': { opponent: '@NYG', result: 'W', score: '20-15' },
                                'DAL-5': { opponent: '@PIT', result: 'L', score: '17-20' },
                                'DAL-6': { opponent: '@DET', result: 'L', score: '38-47' },
                                'DAL-7': { opponent: 'vs SF', result: 'TBD', score: '' },
                                // KC
                                'KC-1': { opponent: 'vs BAL', result: 'W', score: '27-20' },
                                'KC-2': { opponent: '@CIN', result: 'W', score: '26-25' },
                                'KC-3': { opponent: 'vs ATL', result: 'W', score: '22-17' },
                                'KC-4': { opponent: '@LAC', result: 'W', score: '17-10' },
                                'KC-5': { opponent: 'vs NO', result: 'W', score: '26-13' },
                                'KC-6': { opponent: '@BUF', result: 'L', score: '27-30' },
                                'KC-7': { opponent: 'vs LV', result: 'TBD', score: '' },
                                // PIT
                                'PIT-1': { opponent: '@ATL', result: 'W', score: '18-10' },
                                'PIT-2': { opponent: 'vs DEN', result: 'W', score: '13-6' },
                                'PIT-3': { opponent: '@LAC', result: 'W', score: '20-10' },
                                'PIT-4': { opponent: 'vs IND', result: 'W', score: '27-24' },
                                'PIT-5': { opponent: 'vs DAL', result: 'W', score: '20-17' },
                                'PIT-6': { opponent: '@LV', result: 'W', score: '32-13' },
                                'PIT-7': { opponent: 'vs NYJ', result: 'TBD', score: '' },
                                // BUF
                                'BUF-1': { opponent: 'vs ARI', result: 'W', score: '34-28' },
                                'BUF-2': { opponent: '@MIA', result: 'W', score: '31-10' },
                                'BUF-3': { opponent: 'vs JAX', result: 'W', score: '47-10' },
                                'BUF-4': { opponent: 'vs BAL', result: 'W', score: '35-10' },
                                'BUF-5': { opponent: '@HOU', result: 'W', score: '23-20' },
                                'BUF-6': { opponent: 'vs KC', result: 'W', score: '30-27' },
                                'BUF-7': { opponent: '@TEN', result: 'TBD', score: '' },
                                // PHI
                                'PHI-1': { opponent: 'vs GB', result: 'L', score: '29-34' },
                                'PHI-2': { opponent: '@ATL', result: 'W', score: '22-21' },
                                'PHI-3': { opponent: 'vs NO', result: 'W', score: '15-12' },
                                'PHI-4': { opponent: '@TB', result: 'W', score: '33-16' },
                                'PHI-5': { opponent: '@CLE', result: 'W', score: '20-16' },
                                'PHI-6': { opponent: 'vs NYJ', result: 'W', score: '20-14' },
                                'PHI-7': { opponent: 'vs NYG', result: 'TBD', score: '' },
                                // BAL  
                                'BAL-1': { opponent: '@KC', result: 'L', score: '20-27' },
                                'BAL-2': { opponent: 'vs LV', result: 'W', score: '23-13' },
                                'BAL-3': { opponent: 'vs DAL', result: 'W', score: '28-25' },
                                'BAL-4': { opponent: '@BUF', result: 'L', score: '10-35' },
                                'BAL-5': { opponent: 'vs CIN', result: 'L', score: '38-41' },
                                'BAL-6': { opponent: '@WAS', result: 'W', score: '30-23' },
                                'BAL-7': { opponent: 'vs TB', result: 'TBD', score: '' }
                              };
                              const game = gameResults[`${trendFilters.team}-${week}`] || { opponent: `vs OPP`, result: 'TBD', score: '' };
                              const colSpan = trendViewMode === 'summary' ? 3 : 11;
                              
                              return (
                                <th key={week} colSpan={colSpan} className="bg-black text-white font-bold text-center border-l-4 border-r-4 border-gray-900 px-3 py-2">
                                  <div className="text-center">
                                    <div className="text-[15px] tracking-wider font-extrabold">Week {week}</div>
                                    <div className="text-[14px] text-gray-200 mt-1 font-semibold tracking-wide">{game.opponent} - {game.result} {game.score}</div>
                                  </div>
                                </th>
                              );
                            })}
                          </tr>
                          
                          {/* Row 2: Category Headers (Misc, Passing, Rushing, FPTS for QB) */}
                          <tr className="bg-gray-600">
                            {Array.from({length: trendFilters.endWeek - trendFilters.startWeek + 1}, (_, i) => {
                              return (
                                <React.Fragment key={i}>
                                  {trendViewMode === 'summary' ? (
                                    <>
                                      <th colSpan="2" className="bg-gray-700 text-white font-bold text-center text-[14px] py-1 border-r border-gray-500 border-l-4 border-gray-900">Misc.</th>
                                      <th colSpan="1" className="bg-fuchsia-600 text-white font-bold text-center text-[14px] py-1 border-r-4 border-gray-900">FPTS</th>
                                    </>
                                  ) : (
                                    <>
                                      <th colSpan="2" className="bg-gray-700 text-white font-bold text-center text-[14px] py-1 border-r border-gray-500 border-l-4 border-gray-900">Misc.</th>
                                      <th colSpan="5" className="bg-blue-700 text-white font-bold text-center text-[14px] py-1 border-r border-gray-500">Passing</th>
                                      <th colSpan="3" className="bg-green-700 text-white font-bold text-center text-[14px] py-1 border-r border-gray-500">Rushing</th>
                                      <th colSpan="1" className="bg-fuchsia-600 text-white font-bold text-center text-[14px] py-1 border-r-4 border-gray-900">FPTS</th>
                                    </>
                                  )}
                                </React.Fragment>
                              );
                            })}
                          </tr>
                          
                          {/* Row 3: Individual Stat Headers */}
                          <tr className="bg-gray-200">
                            {Array.from({length: trendFilters.endWeek - trendFilters.startWeek + 1}, (_, i) => {
                              return (
                                <React.Fragment key={i}>
                                  {trendViewMode === 'summary' ? (
                                    <>
                                      <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 border-l-4 border-gray-900 w-12">$</th>
                                      <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 w-10">#</th>
                                      <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r-4 border-gray-900 w-12">Pts</th>
                                    </>
                                  ) : (
                                    <>
                                      <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 border-l-4 border-gray-900 w-10">$</th>
                                      <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-400 w-8">#</th>
                                      <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 w-10">Cmp</th>
                                      <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 w-10">Att</th>
                                      <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 w-10">Yds</th>
                                      <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 w-8">TD</th>
                                      <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-400 w-8">Int</th>
                                      <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 w-8">Att</th>
                                      <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 w-10">Yds</th>
                                      <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-400 w-8">TD</th>
                                      <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r-4 border-gray-900 w-12">Pts</th>
                                    </>
                                  )}
                                </React.Fragment>
                              );
                            })}
                          </tr>
                        </thead>
                      
                      <tbody>
                          {/* QB Section */}
                          {trendData.filter(player => player.position === 'QB').length > 0 && (
                            <>
                              {/* QB Position Header */}
                              <tr className="border-t-2 border-slate-400" style={{backgroundColor: '#A9D9F3'}}>
                                <td colSpan="100" className="py-1 px-3 font-bold text-slate-900 text-[12px] uppercase tracking-wide border-b-2 border-slate-400">
                                  QUARTERBACKS
                                </td>
                              </tr>
                              {trendData.filter(player => player.position === 'QB').map((player, playerIndex, qbPlayers) => {
                                const isFirstQB = playerIndex === 0;
                                return (
                                  <tr key={`QB-${player.player_name}`} className="hover:bg-blue-50/30 transition-colors" style={{borderBottom: '1px solid #E0E0E0'}}>
                                    {isFirstQB && (
                                      <td rowSpan={qbPlayers.length} className="sticky left-0 text-gray-900 font-bold text-center align-middle z-20 text-[11px] border-r" style={{backgroundColor: '#EBF5FB', borderRight: '1px solid #E0E0E0', width: '40px'}}>
                                        QB
                                      </td>
                                    )}
                                    <td 
                                      className="sticky left-10 bg-white text-gray-900 font-bold text-left pl-2 z-20 py-1 text-[14px] cursor-pointer hover:bg-blue-50 hover:text-blue-600 transition-colors" 
                                      style={{borderRight: '1px solid #E0E0E0', width: '140px'}}
                                      onClick={() => handlePlayerClick(player)}
                                    >
                                      {player.player_name}
                                    </td>
                                    
                                    {/* Week Data */}
                                    {Array.from({length: trendFilters.endWeek - trendFilters.startWeek + 1}, (_, i) => {
                                      const week = trendFilters.startWeek + i;
                                      
                                      const weekData = player.weeks[week];
                                      const passingAttempts = weekData ? Math.ceil((weekData.passing_yards || 0) / 8.5) : 0;
                                      const passingCompletions = weekData ? Math.ceil(passingAttempts * 0.65) : 0;
                                      const rushingAttempts = weekData ? Math.ceil((weekData.rushing_yards || 0) / 4.5) : 0;
                                      const fantasyPoints = weekData ? (weekData.fantasy_points || 0) : 0;
                                      
                                      return (
                                        <React.Fragment key={week}>
                                          {trendViewMode === 'summary' ? (
                                            <>
                                              <td className="text-center text-[14px] text-gray-900 bg-white py-0.5.5 border-l-4 border-gray-900" style={{borderRight: '1px solid #D1D5DB'}}>
                                                {weekData?.dk_salary ? `$${(weekData.dk_salary/1000).toFixed(1)}k` : '-'}
                                              </td>
                                              <td className="text-center text-[14px] text-gray-900 bg-white py-0.5.5" style={{borderRight: '2px solid #9CA3AF'}}>
                                                {weekData?.snap_count || weekData?.snap_percentage || '-'}
                                              </td>
                                              <td className={`text-center text-[14px] py-0.5.5 font-semibold border-r-4 border-gray-900 ${
                                                fantasyPoints >= 25 ? 'bg-green-100 text-green-800' :
                                                fantasyPoints >= 20 ? 'bg-green-50 text-green-700' :
                                                fantasyPoints >= 15 ? 'bg-yellow-50 text-yellow-700' :
                                                fantasyPoints >= 10 ? 'bg-orange-50 text-orange-700' :
                                                fantasyPoints > 0 ? 'bg-red-50 text-red-700' : 'bg-white text-gray-900'
                                              }`}>
                                                {weekData ? fantasyPoints.toFixed(1) : '-'}
                                              </td>
                                            </>
                                          ) : (
                                            <>
                                              <td className="text-center text-[14px] text-gray-900 bg-white py-0.5.5 border-l-4 border-gray-900" style={{borderRight: '1px solid #D1D5DB'}}>
                                                {weekData?.dk_salary ? `$${(weekData.dk_salary/1000).toFixed(1)}k` : ''}
                                              </td>
                                              <td className="text-center text-[14px] text-gray-900 bg-white py-0.5.5" style={{borderRight: '2px solid #9CA3AF'}}>
                                                {weekData?.snap_count || weekData?.snap_percentage || ''}
                                              </td>
                                              <td className="text-center text-[14px] text-gray-900 bg-white py-0.5.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                                {weekData && weekData.passing_yards > 0 ? passingCompletions : ''}
                                              </td>
                                              <td className="text-center text-[14px] text-gray-900 bg-white py-0.5.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                                {weekData && weekData.passing_yards > 0 ? passingAttempts : ''}
                                              </td>
                                              <td className="text-center text-[14px] text-gray-900 bg-white py-0.5.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                                {weekData && weekData.passing_yards > 0 ? weekData.passing_yards : ''}
                                              </td>
                                              <td className="text-center text-[14px] text-gray-900 bg-white py-0.5.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                                {weekData && weekData.passing_tds > 0 ? weekData.passing_tds : ''}
                                              </td>
                                              <td className="text-center text-[14px] text-gray-900 bg-white py-0.5.5" style={{borderRight: '2px solid #9CA3AF'}}>
                                                {weekData && weekData.interceptions > 0 ? weekData.interceptions : ''}
                                              </td>
                                              <td className="text-center text-[14px] text-gray-900 bg-white py-0.5.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                                {weekData && weekData.rushing_yards > 0 ? rushingAttempts : ''}
                                              </td>
                                              <td className="text-center text-[14px] text-gray-900 bg-white py-0.5.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                                {weekData && weekData.rushing_yards > 0 ? weekData.rushing_yards : ''}
                                              </td>
                                              <td className="text-center text-[14px] text-gray-900 bg-white py-0.5.5" style={{borderRight: '2px solid #9CA3AF'}}>
                                                {weekData && weekData.rushing_tds > 0 ? weekData.rushing_tds : ''}
                                              </td>
                                              <td className={`text-center text-[14px] py-0.5.5 font-semibold border-r-4 border-gray-900 ${
                                                fantasyPoints >= 25 ? 'bg-green-100 text-green-800' :
                                                fantasyPoints >= 20 ? 'bg-green-50 text-green-700' :
                                                fantasyPoints >= 15 ? 'bg-yellow-50 text-yellow-700' :
                                                fantasyPoints >= 10 ? 'bg-orange-50 text-orange-700' :
                                                fantasyPoints > 0 ? 'bg-red-50 text-red-700' : 'bg-white text-gray-900'
                                              }`}>
                                                {weekData ? fantasyPoints.toFixed(1) : ''}
                                              </td>
                                            </>
                                          )
                                        }
                                        </React.Fragment>
                                      );
                                    })}
                                  </tr>
                                );
                              })}
                            </>
                          )}
                        
                        {/* RB/WR/TE Section - New Headers with Receiving */}
                        {(trendData.filter(player => ['RB', 'WR', 'TE'].includes(player.position)).length > 0) && (
                          <>
                            {/* Category Headers Row for RB/WR/TE */}
                            <tr className="bg-gray-600 sticky" style={{top: '120px', zIndex: 15}}>
                              <th className="sticky left-0 bg-gray-600 z-20 border-r-4 border-gray-900"></th>
                              <th className="sticky left-12 bg-gray-600 z-20 border-r-4 border-gray-900"></th>
                              {Array.from({length: trendFilters.endWeek - trendFilters.startWeek + 1}, (_, i) => {
                                return (
                                  <React.Fragment key={i}>
                                    {trendViewMode === 'summary' ? (
                                      <>
                                        <th colSpan="2" className="bg-gray-700 text-white font-bold text-center text-[14px] py-1 border-r border-gray-500 border-l-4 border-gray-900">Misc.</th>
                                        <th colSpan="1" className="bg-fuchsia-600 text-white font-bold text-center text-[14px] py-1 border-r-4 border-gray-900">FPTS</th>
                                      </>
                                    ) : (
                                      <>
                                        <th colSpan="2" className="bg-gray-700 text-white font-bold text-center text-[14px] py-1 border-r border-gray-500 border-l-4 border-gray-900">Misc.</th>
                                        <th colSpan="4" className="bg-orange-600 text-white font-bold text-center text-[14px] py-1 border-r border-gray-500">Receiving</th>
                                        <th colSpan="4" className="bg-green-700 text-white font-bold text-center text-[14px] py-1 border-r border-gray-500">Rushing</th>
                                        <th colSpan="1" className="bg-fuchsia-600 text-white font-bold text-center text-[14px] py-1 border-r-4 border-gray-900">FPTS</th>
                                      </>
                                    )}
                                  </React.Fragment>
                                );
                              })}
                            </tr>
                            
                            {/* Individual Stat Headers for RB/WR/TE */}
                            <tr className="bg-gray-200 sticky" style={{top: '145px', zIndex: 15}}>
                              <th className="sticky left-0 bg-gray-200 z-20 border-r-4 border-gray-900"></th>
                              <th className="sticky left-12 bg-gray-200 z-20 border-r-4 border-gray-900"></th>
                              {Array.from({length: trendFilters.endWeek - trendFilters.startWeek + 1}, (_, i) => {
                                return (
                                  <React.Fragment key={i}>
                                    {trendViewMode === 'summary' ? (
                                      <>
                                        <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 border-l-4 border-gray-900 w-12">$</th>
                                        <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 w-10">#</th>
                                        <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r-4 border-gray-900 w-12">Pts</th>
                                      </>
                                    ) : (
                                      <>
                                        <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 border-l-4 border-gray-900 w-10">$</th>
                                        <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-400 w-8">#</th>
                                        <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 w-8">Tgt</th>
                                        <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 w-8">Rec</th>
                                        <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 w-10">Yds</th>
                                        <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-400 w-8">TD</th>
                                        <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 w-8">Att</th>
                                        <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 w-10">Yds</th>
                                        <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-300 w-8">TD</th>
                                        <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r border-gray-400 w-8">Fum</th>
                                        <th className="bg-white text-gray-900 font-bold text-center text-[14px] py-1 border-r-4 border-gray-900 w-12">Pts</th>
                                      </>
                                    )}
                                  </React.Fragment>
                                );
                              })}
                            </tr>
                          </>
                        )}
                        
                        {/* RB Section */}
                        {trendData.filter(player => player.position === 'RB').length > 0 && (
                          <>
                            {/* RB Position Header */}
                            <tr className="border-t-2 border-slate-400" style={{backgroundColor: '#A8E6A3'}}>
                              <td colSpan="100" className="py-1 px-3 font-bold text-slate-900 text-[12px] uppercase tracking-wide border-b-2 border-slate-400">
                                RUNNING BACKS
                              </td>
                            </tr>
                            {trendData.filter(player => player.position === 'RB').map((player, playerIndex, rbPlayers) => {
                              return (
                                <tr key={`RB-${player.player_name}`} className="bg-emerald-50/30 hover:bg-emerald-100/50 transition-colors border-b border-emerald-100">
                                  <td className="sticky left-0 bg-emerald-500 text-white font-bold text-center text-xs w-12 z-20">
                                    RB
                                  </td>
                                  <td 
                                    className="sticky left-12 bg-gradient-to-r from-emerald-50/90 to-white text-slate-900 font-bold text-left border-r border-emerald-200 pl-3 z-20 py-2 min-w-[140px] text-[14px] cursor-pointer hover:bg-emerald-100 hover:text-emerald-700 transition-colors"
                                    onClick={() => handlePlayerClick(player)}
                                  >
                                    {player.player_name}
                                  </td>
                                  
                                  {/* Week Data */}
                                  {Array.from({length: trendFilters.endWeek - trendFilters.startWeek + 1}, (_, i) => {
                                    const week = trendFilters.startWeek + i;
                                    
                                    const weekData = player.weeks[week];
                                    const passingAttempts = weekData ? Math.ceil((weekData.passing_yards || 0) / 8.5) : 0;
                                    const passingCompletions = weekData ? Math.ceil(passingAttempts * 0.65) : 0;
                                    const rushingAttempts = weekData ? Math.ceil((weekData.rushing_yards || 0) / 4.5) : 0;
                                    const fantasyPoints = weekData ? (weekData.fantasy_points || 0) : 0;
                                    
                                    return (
                                      <React.Fragment key={week}>
                                        {trendViewMode === 'summary' ? (
                                          <>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5 border-l-4 border-gray-900" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData?.dk_salary ? `$${(weekData.dk_salary/1000).toFixed(1)}k` : '-'}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '2px solid #9CA3AF'}}>
                                              {weekData?.snap_count || weekData?.snap_percentage || '-'}
                                            </td>
                                            <td className={`text-center text-[14px] py-0.5 font-semibold border-r-4 border-gray-900 ${
                                              fantasyPoints >= 25 ? 'bg-green-100 text-green-800' :
                                              fantasyPoints >= 20 ? 'bg-green-50 text-green-700' :
                                              fantasyPoints >= 15 ? 'bg-yellow-50 text-yellow-700' :
                                              fantasyPoints >= 10 ? 'bg-orange-50 text-orange-700' :
                                              fantasyPoints > 0 ? 'bg-red-50 text-red-700' : 'bg-white text-gray-900'
                                            }`}>
                                              {weekData ? fantasyPoints.toFixed(1) : '-'}
                                            </td>
                                          </>
                                        ) : (
                                          <>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5 border-l-4 border-gray-900" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData?.dk_salary ? `$${(weekData.dk_salary/1000).toFixed(1)}k` : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '2px solid #9CA3AF'}}>
                                              {weekData?.snap_count || weekData?.snap_percentage || ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.targets > 0 ? weekData.targets : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.receptions > 0 ? weekData.receptions : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.receiving_yards > 0 ? weekData.receiving_yards : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '2px solid #9CA3AF'}}>
                                              {weekData && weekData.receiving_tds > 0 ? weekData.receiving_tds : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.rushing_yards > 0 ? rushingAttempts : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.rushing_yards > 0 ? weekData.rushing_yards : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.rushing_tds > 0 ? weekData.rushing_tds : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '2px solid #9CA3AF'}}>
                                              {weekData && weekData.fumbles_lost > 0 ? weekData.fumbles_lost : ''}
                                            </td>
                                            <td className={`text-center text-[14px] py-0.5 font-semibold border-r-4 border-gray-900 ${
                                              fantasyPoints >= 25 ? 'bg-green-100 text-green-800' :
                                              fantasyPoints >= 20 ? 'bg-green-50 text-green-700' :
                                              fantasyPoints >= 15 ? 'bg-yellow-50 text-yellow-700' :
                                              fantasyPoints >= 10 ? 'bg-orange-50 text-orange-700' :
                                              fantasyPoints > 0 ? 'bg-red-50 text-red-700' : 'bg-white text-gray-900'
                                            }`}>
                                              {weekData ? fantasyPoints.toFixed(1) : ''}
                                            </td>
                                          </>
                                        )
                                        }
                                      </React.Fragment>
                                    );
                                  })}
                                </tr>
                              );
                            })}
                          </>
                        )}
                        
                        {/* WR Section */}
                        {trendData.filter(player => player.position === 'WR').length > 0 && (
                          <>
                            {/* WR Position Header */}
                            <tr className="border-t-2 border-slate-400" style={{backgroundColor: '#FDE68A'}}>
                              <td colSpan="100" className="py-1 px-3 font-bold text-slate-900 text-[12px] uppercase tracking-wide border-b-2 border-slate-400">
                                WIDE RECEIVERS
                              </td>
                            </tr>
                            {trendData.filter(player => player.position === 'WR').map((player, playerIndex, wrPlayers) => {
                              return (
                                <tr key={`WR-${player.player_name}`} className="bg-sky-50/30 hover:bg-sky-100/50 transition-colors border-b border-sky-100">
                                  <td className="sticky left-0 bg-sky-500 text-white font-bold text-center text-xs w-12 z-20">
                                    WR
                                  </td>
                                  <td 
                                    className="sticky left-12 bg-gradient-to-r from-sky-50/90 to-white text-slate-900 font-bold text-left border-r border-sky-200 pl-3 z-20 py-2 min-w-[140px] text-[14px] cursor-pointer hover:bg-sky-100 hover:text-sky-700 transition-colors"
                                    onClick={() => handlePlayerClick(player)}
                                  >
                                    {player.player_name}
                                  </td>
                              
                                  {/* Week Data */}
                                  {Array.from({length: trendFilters.endWeek - trendFilters.startWeek + 1}, (_, i) => {
                                    const week = trendFilters.startWeek + i;
                                    const weekData = player.weeks[week];
                                    const rushingAttempts = weekData ? Math.ceil((weekData.rushing_yards || 0) / 4.5) : 0;
                                    const fantasyPoints = weekData ? (weekData.fantasy_points || 0) : 0;
                                    
                                    return (
                                      <React.Fragment key={week}>
                                        {trendViewMode === 'summary' ? (
                                          <>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5 border-l-4 border-gray-900" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData?.dk_salary ? `$${(weekData.dk_salary/1000).toFixed(1)}k` : '-'}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '2px solid #9CA3AF'}}>
                                              {weekData?.snap_count || weekData?.snap_percentage || '-'}
                                            </td>
                                            <td className={`text-center text-[14px] py-0.5 font-semibold border-r-4 border-gray-900 ${
                                              fantasyPoints >= 25 ? 'bg-green-100 text-green-800' :
                                              fantasyPoints >= 20 ? 'bg-green-50 text-green-700' :
                                              fantasyPoints >= 15 ? 'bg-yellow-50 text-yellow-700' :
                                              fantasyPoints >= 10 ? 'bg-orange-50 text-orange-700' :
                                              fantasyPoints > 0 ? 'bg-red-50 text-red-700' : 'bg-white text-gray-900'
                                            }`}>
                                              {weekData ? fantasyPoints.toFixed(1) : '-'}
                                            </td>
                                          </>
                                        ) : (
                                          <>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5 border-l-4 border-gray-900" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData?.dk_salary ? `$${(weekData.dk_salary/1000).toFixed(1)}k` : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '2px solid #9CA3AF'}}>
                                              {weekData?.snap_count || weekData?.snap_percentage || ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.targets > 0 ? weekData.targets : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.receptions > 0 ? weekData.receptions : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.receiving_yards > 0 ? weekData.receiving_yards : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '2px solid #9CA3AF'}}>
                                              {weekData && weekData.receiving_tds > 0 ? weekData.receiving_tds : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.rushing_yards > 0 ? rushingAttempts : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.rushing_yards > 0 ? weekData.rushing_yards : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.rushing_tds > 0 ? weekData.rushing_tds : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '2px solid #9CA3AF'}}>
                                              {weekData && weekData.fumbles_lost > 0 ? weekData.fumbles_lost : ''}
                                            </td>
                                            <td className={`text-center text-[14px] py-0.5 font-semibold border-r-4 border-gray-900 ${
                                              fantasyPoints >= 25 ? 'bg-green-100 text-green-800' :
                                              fantasyPoints >= 20 ? 'bg-green-50 text-green-700' :
                                              fantasyPoints >= 15 ? 'bg-yellow-50 text-yellow-700' :
                                              fantasyPoints >= 10 ? 'bg-orange-50 text-orange-700' :
                                              fantasyPoints > 0 ? 'bg-red-50 text-red-700' : 'bg-white text-gray-900'
                                            }`}>
                                              {weekData ? fantasyPoints.toFixed(1) : ''}
                                            </td>
                                          </>
                                        )
                                        }
                                      </React.Fragment>
                                    );
                                  })}
                            </tr>
                          );
                        })}
                          </>
                        )}
                        
                        {/* TE Section */}
                        {trendData.filter(player => player.position === 'TE').length > 0 && (
                          <>
                            {/* TE Position Header */}
                            <tr className="border-t-2 border-slate-400" style={{backgroundColor: '#FFAA99'}}>
                              <td colSpan="100" className="py-1 px-3 font-bold text-slate-900 text-[12px] uppercase tracking-wide border-b-2 border-slate-400">
                                TIGHT ENDS
                              </td>
                            </tr>
                            {trendData.filter(player => player.position === 'TE').map((player, playerIndex, tePlayers) => {
                              return (
                                <tr key={`TE-${player.player_name}`} className="bg-amber-50/30 hover:bg-amber-100/50 transition-colors border-b border-amber-100">
                                  <td className="sticky left-0 bg-amber-500 text-white font-bold text-center text-xs w-12 z-20">
                                    TE
                                  </td>
                                  <td 
                                    className="sticky left-12 bg-gradient-to-r from-amber-50/90 to-white text-slate-900 font-bold text-left border-r border-amber-200 pl-3 z-20 py-2 min-w-[140px] text-[14px] cursor-pointer hover:bg-amber-100 hover:text-amber-700 transition-colors"
                                    onClick={() => handlePlayerClick(player)}
                                  >
                                    {player.player_name}
                                  </td>
                                  
                                  {/* Week Data */}
                                  {Array.from({length: trendFilters.endWeek - trendFilters.startWeek + 1}, (_, i) => {
                                    const week = trendFilters.startWeek + i;
                                    
                                    const weekData = player.weeks[week];
                                    const passingAttempts = weekData ? Math.ceil((weekData.passing_yards || 0) / 8.5) : 0;
                                    const passingCompletions = weekData ? Math.ceil(passingAttempts * 0.65) : 0;
                                    const rushingAttempts = weekData ? Math.ceil((weekData.rushing_yards || 0) / 4.5) : 0;
                                    const fantasyPoints = weekData ? (weekData.fantasy_points || 0) : 0;
                                    
                                    return (
                                      <React.Fragment key={week}>
                                        {trendViewMode === 'summary' ? (
                                          <>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5 border-l-4 border-gray-900" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData?.dk_salary ? `$${(weekData.dk_salary/1000).toFixed(1)}k` : '-'}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '2px solid #9CA3AF'}}>
                                              {weekData?.snap_count || weekData?.snap_percentage || '-'}
                                            </td>
                                            <td className={`text-center text-[14px] py-0.5 font-semibold border-r-4 border-gray-900 ${
                                              fantasyPoints >= 25 ? 'bg-green-100 text-green-800' :
                                              fantasyPoints >= 20 ? 'bg-green-50 text-green-700' :
                                              fantasyPoints >= 15 ? 'bg-yellow-50 text-yellow-700' :
                                              fantasyPoints >= 10 ? 'bg-orange-50 text-orange-700' :
                                              fantasyPoints > 0 ? 'bg-red-50 text-red-700' : 'bg-white text-gray-900'
                                            }`}>
                                              {weekData ? fantasyPoints.toFixed(1) : '-'}
                                            </td>
                                          </>
                                        ) : (
                                          <>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5 border-l-4 border-gray-900" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData?.dk_salary ? `$${(weekData.dk_salary/1000).toFixed(1)}k` : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '2px solid #9CA3AF'}}>
                                              {weekData?.snap_count || weekData?.snap_percentage || ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.targets > 0 ? weekData.targets : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.receptions > 0 ? weekData.receptions : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.receiving_yards > 0 ? weekData.receiving_yards : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '2px solid #9CA3AF'}}>
                                              {weekData && weekData.receiving_tds > 0 ? weekData.receiving_tds : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.rushing_yards > 0 ? rushingAttempts : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.rushing_yards > 0 ? weekData.rushing_yards : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '1px solid #D1D5DB'}}>
                                              {weekData && weekData.rushing_tds > 0 ? weekData.rushing_tds : ''}
                                            </td>
                                            <td className="text-center text-[14px] text-gray-900 bg-white py-0.5" style={{borderRight: '2px solid #9CA3AF'}}>
                                              {weekData && weekData.fumbles_lost > 0 ? weekData.fumbles_lost : ''}
                                            </td>
                                            <td className={`text-center text-[14px] py-0.5 font-semibold border-r-4 border-gray-900 ${
                                              fantasyPoints >= 25 ? 'bg-green-100 text-green-800' :
                                              fantasyPoints >= 20 ? 'bg-green-50 text-green-700' :
                                              fantasyPoints >= 15 ? 'bg-yellow-50 text-yellow-700' :
                                              fantasyPoints >= 10 ? 'bg-orange-50 text-orange-700' :
                                              fantasyPoints > 0 ? 'bg-red-50 text-red-700' : 'bg-white text-gray-900'
                                            }`}>
                                              {weekData ? fantasyPoints.toFixed(1) : ''}
                                            </td>
                                          </>
                                        )
                                        }
                                      </React.Fragment>
                                    );
                                  })}
                                </tr>
                              );
                            })}
                          </>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
        </div>
      </div>
    </div>
  );
};

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<FantasyDashboard />} />
          <Route path="/data-table" element={<FantasyDashboard />} />
          <Route path="/trend-tool" element={<FantasyDashboard />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
