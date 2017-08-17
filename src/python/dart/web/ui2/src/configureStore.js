import { createStore, applyMiddleware } from 'redux';
import promise from 'redux-promise';
import logger from 'redux-logger';
import thunk from 'redux-thunk';
import { routerMiddleware } from 'react-router-redux'

import { reducer } from 'api/';


const configureStore = (history) => {
  const middlewares = [
      thunk,
      promise,
      routerMiddleware(history),
  ];

  if (true || process.env.NODE_ENV !== 'production') {
      middlewares.push(logger);
  }

  return createStore(reducer, applyMiddleware(...middlewares));
};


export default configureStore;
