declare module 'animejs' {
  interface AnimeParams {
    targets?: any
    duration?: number
    delay?: number | Function
    easing?: string
    round?: number
    loop?: boolean
    opacity?: any
    translateX?: any
    translateY?: any
    scale?: any
    update?: () => void
    [key: string]: any
  }

  interface AnimeTimelineInstance {
    add(params: AnimeParams, offset?: string | number): AnimeTimelineInstance
  }

  interface AnimeStatic {
    (params: AnimeParams): any
    timeline(params?: AnimeParams): AnimeTimelineInstance
    stagger(value: number, options?: any): any
    random(min: number, max: number): number
  }

  const anime: AnimeStatic
  export default anime
}
