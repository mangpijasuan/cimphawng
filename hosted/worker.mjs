import {handleApi} from './lib/hosted-api.mjs';
export default {
 async fetch(request,env){
  if(new URL(request.url).pathname.startsWith('/api/'))return handleApi(request,env.DB,env.SITE_ORIGIN?{origin:env.SITE_ORIGIN}:{});
  return env.ASSETS.fetch(request);
 }
};
