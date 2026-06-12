import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

const MIGRATION_URL = "https://paperswithcode.co/ai-deadlines";
const CONFERENCES_URL = "https://paperswithcode.co/conferences";
const FEEDBACK_ISSUES_URL = "https://github.com/huggingface/paperswithcode-feedback/issues";

const MigrationDialog = () => {
  const [open, setOpen] = useState(true);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="gap-6 p-8 sm:max-w-2xl">
        <DialogHeader className="space-y-3">
          <DialogTitle className="text-2xl">This app has moved</DialogTitle>
          <DialogDescription className="text-lg">
            This app has been migrated to{" "}
            <a
              href={MIGRATION_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:underline"
            >
              paperswithcode.co/ai-deadlines
            </a>
            .
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-5 text-base leading-relaxed text-muted-foreground">
          <p>The new website includes:</p>
          <ul className="list-disc space-y-2 pl-6">
            <li>Save deadlines to your Apple or Google Calendar</li>
            <li>
              Browse conference papers by domain at{" "}
              <a
                href={CONFERENCES_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                paperswithcode.co/conferences
              </a>
            </li>
            <li>Sign in with your Hugging Face account and save your favorite papers (optional)</li>
          </ul>
          <p>
            To submit new conference data, or raise any feedback, please open an issue at{" "}
            <a
              href={FEEDBACK_ISSUES_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:underline"
            >
              github.com/huggingface/paperswithcode-feedback/issues
            </a>
            .
          </p>
        </div>
        <DialogFooter className="sm:justify-start">
          <Button asChild size="lg" className="text-base">
            <a href={MIGRATION_URL} target="_blank" rel="noopener noreferrer">
              Visit the new site
            </a>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default MigrationDialog;
