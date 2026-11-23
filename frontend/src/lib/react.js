// React and htm are loaded as globals by index.html (vendored UMD builds).
// Re-export them so every module imports from one place.
const { React, ReactDOM, htm } = window;

export { React, ReactDOM };
export const { useState, useEffect, useCallback, useRef } = React;
export const html = htm.bind(React.createElement);
