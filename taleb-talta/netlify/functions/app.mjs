import { dispatch } from "../server.mjs";

export default async function handler(req, context) {
  return dispatch(req, context, { timeoutMs: 55000 });
}

export const config = {
  path: ["/", "/*"],
  excludedPath: ["/static/*"],
  preferStatic: true,
};
