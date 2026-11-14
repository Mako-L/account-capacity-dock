// deno-lint-ignore-file
/* eslint-disable */
// biome-ignore: needed import
import type { OneRouter } from 'one'

declare module 'one' {
  export namespace OneRouter {
    export interface __routes<T extends string = string> extends Record<string, unknown> {
      StaticRoutes:
        | `/`
        | `/(tabs)`
        | `/(tabs)/`
        | `/(tabs)/agents`
        | `/_sitemap`
        | `/agents`
        | `/settings`
      DynamicRoutes:
        | `/account/${OneRouter.SingleRoutePart<T>}`
        | `/agent/${OneRouter.SingleRoutePart<T>}`
      DynamicRouteTemplate:
        | `/account/[id]`
        | `/agent/[id]`
      IsTyped: true
      RouteTypes: {
        '/account/[id]': RouteInfo<{ id: string }, '/account/[id]'>
        '/agent/[id]': RouteInfo<{ id: string }, '/agent/[id]'>
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