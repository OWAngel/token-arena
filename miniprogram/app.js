const config = require('./config');
App({
  globalData: { apiBase: config.API_BASE.replace(/\/$/, ''), publicBoardUrl: config.PUBLIC_BOARD_URL, enrollmentOpen: config.ENROLLMENT_OPEN === true },
  onLaunch() {
    // Login is initiated by a user action, never by merely opening the board.
  }
});
