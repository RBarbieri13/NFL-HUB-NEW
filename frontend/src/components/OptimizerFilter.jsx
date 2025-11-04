import React, { useState, useEffect } from 'react';
import { Filter } from 'lucide-react';

const OptimizerFilter = ({ 
  isVisible, 
  onClose,
  currentPosition,
  currentWeek,
  onPositionChange,
  onWeekChange 
}) => {
  const [selectedPlatform, setSelectedPlatform] = useState(() => {
    const saved = localStorage.getItem('optimizer-platform');
    return saved || 'draftkings';
  });
  
  const [selectedPositions, setSelectedPositions] = useState(() => {
    const saved = localStorage.getItem('optimizer-positions');
    return saved ? JSON.parse(saved) : [currentPosition || 'QB'];
  });
  
  const [isExpanded, setIsExpanded] = useState(() => {
    const saved = localStorage.getItem('optimizer-expanded');
    return saved === 'true';
  });
  
  const [selectedGames, setSelectedGames] = useState(() => {
    const saved = localStorage.getItem('optimizer-games');
    return saved ? JSON.parse(saved) : [];
  });

  useEffect(() => {
    localStorage.setItem('optimizer-platform', selectedPlatform);
  }, [selectedPlatform]);

  useEffect(() => {
    localStorage.setItem('optimizer-positions', JSON.stringify(selectedPositions));
  }, [selectedPositions]);

  useEffect(() => {
    localStorage.setItem('optimizer-expanded', isExpanded.toString());
  }, [isExpanded]);

  useEffect(() => {
    localStorage.setItem('optimizer-games', JSON.stringify(selectedGames));
  }, [selectedGames]);

  const toggleFilter = () => {
    setIsExpanded(!isExpanded);
  };

  const selectPlatform = (platform) => {
    setSelectedPlatform(platform);
  };

  const togglePosition = (position) => {
    let newPositions;
    if (selectedPositions.includes(position)) {
      newPositions = selectedPositions.filter(p => p !== position);
    } else {
      newPositions = [...selectedPositions, position];
    }
    setSelectedPositions(newPositions);
    
    if (onPositionChange && newPositions.length > 0) {
      onPositionChange(newPositions[0]);
    }
  };

  const toggleGame = (gameId) => {
    setSelectedGames(prev => 
      prev.includes(gameId) 
        ? prev.filter(id => id !== gameId)
        : [...prev, gameId]
    );
  };

  const getPlatformBadge = () => {
    const badges = {
      'draftkings': 'DK',
      'fanduel': 'FD',
      'yahoo': 'Y!'
    };
    return badges[selectedPlatform];
  };

  const games = [
    { id: 'min-lac', day: 'Thursday', time: '8:15 PM', away: 'MIN', home: 'LAC', awayScore: 27, homeScore: 20, final: true },
    { id: 'mia-atl', day: 'Sunday 1:00 PM', time: '1:00 PM', away: 'MIA', home: 'ATL' },
    { id: 'chi-bal', day: 'Sunday 1:00 PM', time: '1:00 PM', away: 'CHI', home: 'BAL' },
    { id: 'buf-car', day: 'Sunday 1:00 PM', time: '1:00 PM', away: 'BUF', home: 'CAR' },
    { id: 'nyj-cin', day: 'Sunday 1:00 PM', time: '1:00 PM', away: 'NYJ', home: 'CIN' },
    { id: 'sf-hou', day: 'Sunday 1:00 PM', time: '1:00 PM', away: 'SF', home: 'HOU' },
    { id: 'cle-ne', day: 'Sunday 1:00 PM', time: '1:00 PM', away: 'CLE', home: 'NE' },
    { id: 'nyg-phi', day: 'Sunday 1:00 PM', time: '1:00 PM', away: 'NYG', home: 'PHI' },
    { id: 'tb-no', day: 'Sunday 1:00 PM', time: '1:00 PM', away: 'TB', home: 'NO' },
    { id: 'dal-den', day: 'Sunday Late', time: '4:05 PM', away: 'DAL', home: 'DEN' },
    { id: 'ten-ind', day: 'Sunday Late', time: '4:25 PM', away: 'TEN', home: 'IND' },
    { id: 'gb-pit', day: 'Sunday Late', time: '4:25 PM', away: 'GB', home: 'PIT' },
    { id: 'was-kc', day: 'Monday', time: '8:15 PM', away: 'WAS', home: 'KC' }
  ];

  const groupedGames = games.reduce((acc, game) => {
    if (!acc[game.day]) {
      acc[game.day] = [];
    }
    acc[game.day].push(game);
    return acc;
  }, {});

  if (!isVisible) return null;

  return (
    <div className="optimizer-filter-container fixed top-20 left-4 z-40 max-w-[650px]">
      <div className="bg-white rounded-lg shadow-lg border border-gray-200">
        <div 
          className={`optimizer-filter-header px-3 py-2.5 flex items-center justify-between cursor-pointer ${
            isExpanded ? 'rounded-t-lg' : 'rounded-lg'
          }`}
          onClick={toggleFilter}
        >
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-blue-600" />
            <h2 className="text-sm font-bold text-gray-900">NFL Optimizer</h2>
            <span className="optimizer-badge optimizer-badge-blue">{getPlatformBadge()}</span>
            <span className="optimizer-badge optimizer-badge-green">{selectedGames.length}</span>
            <span className="optimizer-badge optimizer-badge-blue">BETA</span>
          </div>
          <button className="p-1 hover:bg-white/50 rounded transition-colors">
            <svg 
              className={`optimizer-chevron w-4 h-4 text-gray-700 transition-transform ${
                isExpanded ? 'rotate-180' : ''
              }`}
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"/>
            </svg>
          </button>
        </div>

        <div className={`optimizer-filter-content ${isExpanded ? 'expanded' : ''}`}>
          <div className="p-3 space-y-3">
            
            <div className="optimizer-section-bg optimizer-section-border">
              <div className="flex gap-1.5 mb-2">
                {['draftkings', 'fanduel', 'yahoo'].map(platform => (
                  <button
                    key={platform}
                    onClick={() => selectPlatform(platform)}
                    className={`optimizer-toggle-btn flex-1 px-2.5 py-1.5 rounded text-[0.7rem] font-medium ${
                      selectedPlatform === platform
                        ? 'optimizer-toggle-active'
                        : 'bg-white text-gray-700 border border-gray-300'
                    }`}
                  >
                    {platform === 'draftkings' ? 'DraftKings' : platform === 'fanduel' ? 'FanDuel' : 'Yahoo'}
                  </button>
                ))}
              </div>
              <div className="flex gap-1.5">
                <select className="flex-1 px-2.5 py-1.5 text-[0.7rem] text-gray-700 bg-white border border-gray-300 rounded optimizer-dropdown-select">
                  <option>2025 Regular Season, Week 8</option>
                  <option>2025 Regular Season, Week 7</option>
                  <option>2025 Regular Season, Week 6</option>
                </select>
                <select className="flex-1 px-2.5 py-1.5 text-[0.7rem] text-gray-700 bg-white border border-gray-300 rounded optimizer-dropdown-select">
                  <option>Thu-Mon, 13 Games | Classic</option>
                  <option>Sun-Mon, 12 Games | Classic</option>
                  <option>Primetime, 2 Games</option>
                </select>
              </div>
            </div>

            <div className="optimizer-section-bg optimizer-section-border">
              <div className="text-[0.65rem] font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Positions</div>
              <div className="flex flex-wrap gap-1.5">
                {['QB', 'RB', 'WR', 'TE', 'FLEX', 'DST'].map(position => (
                  <button
                    key={position}
                    onClick={() => togglePosition(position)}
                    className={`optimizer-toggle-btn px-3 py-1 rounded text-[0.7rem] font-medium ${
                      selectedPositions.includes(position)
                        ? 'optimizer-toggle-active'
                        : 'bg-white text-gray-700 border border-gray-300'
                    }`}
                  >
                    {position}
                  </button>
                ))}
              </div>
            </div>

            <div className="optimizer-section-bg optimizer-section-border">
              <div className="text-[0.65rem] font-semibold text-gray-600 mb-2 uppercase tracking-wide">Select Games</div>
              
              <div className="max-h-[320px] overflow-y-auto pr-1">
                {Object.entries(groupedGames).map(([day, dayGames]) => (
                  <div key={day}>
                    <div className="optimizer-day-separator">
                      <span className="optimizer-day-label">{day}</span>
                    </div>
                    <div className="optimizer-games-grid mb-3">
                      {dayGames.map(game => (
                        <div
                          key={game.id}
                          onClick={() => toggleGame(game.id)}
                          className={`optimizer-game-card ${
                            selectedGames.includes(game.id) ? 'selected border-blue-500' : 'border-gray-300'
                          }`}
                        >
                          <div className="flex-shrink-0">
                            {game.final && <div className="optimizer-final-badge">FINAL</div>}
                            <div className="optimizer-game-time">{game.time}</div>
                          </div>
                          <span className="text-xs font-medium">{game.away}</span>
                          {game.awayScore !== undefined && (
                            <>
                              <span className={`optimizer-game-score ${game.awayScore > game.homeScore ? 'optimizer-game-winner' : ''}`}>
                                {game.awayScore}
                              </span>
                              <span className="optimizer-vs-indicator">@</span>
                              <span className={`optimizer-game-score ${game.homeScore > game.awayScore ? 'optimizer-game-winner' : ''}`}>
                                {game.homeScore}
                              </span>
                            </>
                          )}
                          {game.awayScore === undefined && (
                            <span className="optimizer-vs-indicator">@</span>
                          )}
                          <span className="text-xs font-medium">{game.home}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between text-[0.7rem] pt-1 border-t border-gray-200">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" className="w-3.5 h-3.5 text-blue-600 rounded" defaultChecked />
                <span className="text-gray-700 font-medium">Show completed games</span>
              </label>
              <button 
                className="optimizer-action-btn"
                onClick={() => {
                  setSelectedGames([]);
                  setSelectedPositions([currentPosition || 'QB']);
                }}
              >
                Clear all filters
              </button>
            </div>

          </div>
        </div>

      </div>
    </div>
  );
};

export default OptimizerFilter;
