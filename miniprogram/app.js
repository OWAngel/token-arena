const config = require('./config');
App({
  globalData: { apiBase: config.API_BASE.replace(/\/$/, ''), publicBoardUrl: config.PUBLIC_BOARD_URL },
  onLaunch() {
    // Login is initiated by a user action, never by merely opening the board.
  }
});
