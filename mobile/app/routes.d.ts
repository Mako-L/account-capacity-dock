// deno-lint-ignore-file
/* eslint-disable */
// biome-ignore: needed import
import type { OneRouter } from 'one'

declare module 'one' {
  export namespace OneRouter {
    export interface __routes<T extends string = string> extends Record<string, unknown> {
      StaticRoutes:
        | `/`
        | `/_sitemap`
        | `/settings`
      DynamicRoutes: `/account/${OneRouter.SingleRoutePart<T>}`
      DynamicRouteTemplate: `/account/[id]`
      IsTyped: true
      RouteTypes: {
        '/account/[id]': RouteInfo<{ id: string }, '/account/[id]'>
      }
    }
  }
}

/**
 * Helper type for route information
 */
type RouteInfo<Params = Record<string, never>, Path extends string = string> = {
  Params: Params
  LoaderProps: import('one').LoaderProps<Params, OneRouter.LoaderSearchParams<Path>>
}