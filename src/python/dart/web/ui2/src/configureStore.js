import { createStore, combineReducers, applyMiddleware } from 'redux';
import promise from 'redux-promise';
import logger from 'redux-logger';
import thunk from 'redux-thunk';
import { routerMiddleware, routerReducer } from 'react-router-redux'

import reducers from 'reducers/';


const configureStore = (history) => {
  const middlewares = [
      thunk,
      promise,
      routerMiddleware(history),
  ];

  if (true || process.env.NODE_ENV !== 'production') {
      middlewares.push(logger);
  }

  return createStore(
      combineReducers({
          ...reducers,
          routerReducer
      }),
      applyMiddleware(...middlewares)
  );
};


export default configureStore;
