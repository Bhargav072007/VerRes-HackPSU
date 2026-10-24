import { cn } from "@/lib/utils";

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn(
        "animate-[pulse_360ms_ease-in-out_infinite] rounded-md bg-accent",
        className,
      )}
      {...props}
    />
  );
}

export { Skeleton };
