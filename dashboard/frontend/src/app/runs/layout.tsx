// Static-export-friendly layout for the runs section. The dynamic
// segment was dropped (see ./page.tsx for the rationale) so this is a
// pure passthrough — kept around as the natural place to add shared
// chrome later without restructuring the route tree.
export default function RunsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
