import { Apple, Monitor, Download, Cpu, HardDrive, MemoryStick, Box } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const APP_VERSION = "1.0.1";
const REPO = "your-org/ectoform-desktop"; // TODO: replace with real GitHub slug
const RELEASE_BASE = `https://github.com/${REPO}/releases/latest/download`;

type Platform = {
  id: string;
  name: string;
  icon: typeof Apple;
  badge: string;
  commercialFile: string;
  educationFile: string;
  requirements: { icon: typeof Cpu; label: string; value: string }[];
};

const platforms: Platform[] = [
  {
    id: "windows",
    name: "Windows",
    icon: Monitor,
    badge: "64-bit installer",
    commercialFile: `ECTOFORM-Setup-${APP_VERSION}.exe`,
    educationFile: `ECTOFORM-Education-Setup-${APP_VERSION}.exe`,
    requirements: [
      { icon: Monitor, label: "OS", value: "Windows 10 or 11 (64-bit)" },
      { icon: Cpu, label: "CPU", value: "x86_64, 4 cores or more" },
      { icon: MemoryStick, label: "RAM", value: "8 GB minimum (16 GB recommended)" },
      { icon: Box, label: "GPU", value: "DirectX 12 / Vulkan compatible, 2 GB VRAM" },
      { icon: HardDrive, label: "Disk", value: "1.5 GB free space" },
    ],
  },
  {
    id: "macos",
    name: "macOS (Apple Silicon)",
    icon: Apple,
    badge: "M1 / M2 / M3 / M4",
    commercialFile: `ECTOFORM-${APP_VERSION}-macOS-arm64.dmg`,
    educationFile: `ECTOFORM-Education-${APP_VERSION}-macOS-arm64.dmg`,
    requirements: [
      { icon: Apple, label: "OS", value: "macOS 11 Big Sur or newer" },
      { icon: Cpu, label: "CPU", value: "Apple Silicon (M1 or newer)" },
      { icon: MemoryStick, label: "RAM", value: "8 GB minimum (16 GB recommended)" },
      { icon: Box, label: "GPU", value: "Integrated Apple GPU (Metal)" },
      { icon: HardDrive, label: "Disk", value: "1.5 GB free space" },
    ],
  },
];

const Index = () => {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <div className="container mx-auto flex items-center justify-between px-6 py-5">
          <div className="flex items-center gap-2">
            <Box className="h-6 w-6 text-primary" />
            <span className="text-lg font-semibold tracking-tight">ECTOFORM</span>
          </div>
          <Badge variant="secondary">v{APP_VERSION}</Badge>
        </div>
      </header>

      <main className="container mx-auto px-6 py-16">
        <section className="mx-auto max-w-2xl text-center">
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">Download ECTOFORM</h1>
          <p className="mt-4 text-muted-foreground">
            3D file analyser for jewelry design. Choose your platform and edition below.
          </p>
        </section>

        <section className="mt-14 grid gap-6 md:grid-cols-2">
          {platforms.map((p) => {
            const Icon = p.icon;
            return (
              <Card key={p.id} className="flex flex-col">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Icon className="h-7 w-7" />
                      <CardTitle>{p.name}</CardTitle>
                    </div>
                    <Badge variant="outline">{p.badge}</Badge>
                  </div>
                  <CardDescription>Native build for {p.name}.</CardDescription>
                </CardHeader>

                <CardContent className="flex flex-1 flex-col gap-6">
                  <div>
                    <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                      System requirements
                    </h3>
                    <ul className="space-y-2 text-sm">
                      {p.requirements.map((r) => {
                        const RI = r.icon;
                        return (
                          <li key={r.label} className="flex items-start gap-3">
                            <RI className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                            <span>
                              <span className="font-medium">{r.label}:</span>{" "}
                              <span className="text-muted-foreground">{r.value}</span>
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  </div>

                  <div className="mt-auto flex flex-col gap-2">
                    <Button asChild>
                      <a href={`${RELEASE_BASE}/${p.commercialFile}`}>
                        <Download className="mr-2 h-4 w-4" />
                        Download Commercial
                      </a>
                    </Button>
                    <Button asChild variant="outline">
                      <a href={`${RELEASE_BASE}/${p.educationFile}`}>
                        <Download className="mr-2 h-4 w-4" />
                        Download Education
                      </a>
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </section>

        <section className="mx-auto mt-14 max-w-2xl text-center text-sm text-muted-foreground">
          <p>
            Intel Mac (x86_64) is no longer supported. On Intel Macs, please use the Windows build via Boot Camp or
            an alternative machine.
          </p>
          <p className="mt-2">
            All releases are published on{" "}
            <a
              href={`https://github.com/${REPO}/releases/latest`}
              className="underline underline-offset-4 hover:text-foreground"
            >
              GitHub Releases
            </a>
            . SHA-256 checksums are available alongside each installer.
          </p>
        </section>
      </main>
    </div>
  );
};

export default Index;
