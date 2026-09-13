import type { SVGProps } from "react";
import { useId } from "react";

import { cn } from "@/lib/utils";

type LogoProps = SVGProps<SVGSVGElement> & {
  className?: string;
  title?: string;
};

/** Product mark — teal/cyan Lark node (not purple AI cliché). */
export function NlmLogo({ className, title = "Nexus Lark Mind", ...rest }: LogoProps) {
  const gid = useId().replace(/:/g, "");
  return (
    <svg
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("shrink-0", className)}
      role="img"
      aria-label={title || undefined}
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      <rect width="40" height="40" rx="10" fill={`url(#${gid})`} />
      <path
        d="M10 26V14l8 8 8-8v12"
        stroke="#F4FBFF"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="28.5" cy="12.5" r="2.2" fill="#7EE0C8" />
      <defs>
        <linearGradient id={gid} x1="6" y1="4" x2="36" y2="38" gradientUnits="userSpaceOnUse">
          <stop stopColor="#0F766E" />
          <stop offset="0.55" stopColor="#0E7490" />
          <stop offset="1" stopColor="#155E75" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export function FeishuLogo({ className, title = "飞书", ...rest }: LogoProps) {
  return (
    <svg viewBox="0 0 32 32" className={cn("shrink-0", className)} role="img" aria-label={title} {...rest}>
      <title>{title}</title>
      <rect width="32" height="32" rx="8" fill="#3370FF" />
      <path
        d="M9 22.5V9.5h5.2c2.9 0 4.7 1.55 4.7 3.9 0 1.55-.85 2.8-2.25 3.35L19.6 22.5h-3.1l-2.55-4.9H12.2v4.9H9zm3.2-7.35h1.85c1.35 0 2.15-.7 2.15-1.75s-.8-1.7-2.15-1.7H12.2v3.45z"
        fill="#fff"
      />
    </svg>
  );
}

export function DingTalkLogo({ className, title = "钉钉", ...rest }: LogoProps) {
  return (
    <svg viewBox="0 0 32 32" className={cn("shrink-0", className)} role="img" aria-label={title} {...rest}>
      <title>{title}</title>
      <rect width="32" height="32" rx="8" fill="#0089FF" />
      <path
        d="M16.1 7.2c-3.9 0-6.6 2.2-6.6 5.35 0 1.7.75 3.15 2.05 4.15l-.55 2.95 3.05-1.55c.65.15 1.3.25 2.05.25 3.9 0 6.6-2.2 6.6-5.35S20 7.2 16.1 7.2zm-1.05 7.7h-1.85v-4.4h1.85v4.4zm3.9 0h-1.85v-4.4H19v4.4z"
        fill="#fff"
      />
    </svg>
  );
}

export function WeComLogo({ className, title = "企业微信", ...rest }: LogoProps) {
  return (
    <svg viewBox="0 0 32 32" className={cn("shrink-0", className)} role="img" aria-label={title} {...rest}>
      <title>{title}</title>
      <rect width="32" height="32" rx="8" fill="#2B7BD6" />
      <circle cx="12.2" cy="14" r="3.2" fill="#fff" opacity="0.95" />
      <circle cx="20.2" cy="14" r="3.2" fill="#fff" opacity="0.75" />
      <path
        d="M8.5 21.2c1.4-1.7 3.3-2.6 5.5-2.6 1.1 0 2.1.2 3 .6 1.2-.9 2.7-1.4 4.3-1.4 1.5 0 2.9.4 4 1.2"
        stroke="#fff"
        strokeWidth="1.6"
        strokeLinecap="round"
        fill="none"
        opacity="0.9"
      />
    </svg>
  );
}

export function WebChannelLogo({ className, title = "Web", ...rest }: LogoProps) {
  return (
    <svg viewBox="0 0 32 32" className={cn("shrink-0", className)} role="img" aria-label={title} {...rest}>
      <title>{title}</title>
      <rect width="32" height="32" rx="8" fill="#0F766E" />
      <circle cx="16" cy="16" r="7.2" stroke="#ECFEFF" strokeWidth="1.8" fill="none" />
      <path d="M9 16h14M16 9c2.4 2.2 2.4 11.6 0 14M16 9c-2.4 2.2-2.4 11.6 0 14" stroke="#A5F3FC" strokeWidth="1.4" fill="none" />
    </svg>
  );
}

export function ChannelLogo({
  kind,
  className,
}: {
  kind?: string;
  className?: string;
}) {
  const k = (kind || "").toLowerCase();
  if (k === "feishu" || k === "lark") return <FeishuLogo className={className} />;
  if (k === "dingtalk" || k === "dingding") return <DingTalkLogo className={className} />;
  if (k === "wecom" || k === "wechat_work" || k === "wxwork") return <WeComLogo className={className} />;
  if (k === "web") return <WebChannelLogo className={className} />;
  return <NlmLogo className={className} />;
}
