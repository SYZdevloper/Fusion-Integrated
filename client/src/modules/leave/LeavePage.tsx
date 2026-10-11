import { Card, Container, Stack, Text, Title } from "@mantine/core";
import { PageHeader } from "../../ui/components/PageHeader";

interface LeavePageProps {
  view: "apply" | "mine" | "balances" | "substitute" | "approvals" | "calendar" | "admin";
}

const titles: Record<LeavePageProps["view"], { title: string; subtitle: string }> = {
  apply: { title: "Apply Leave", subtitle: "Submit a new leave application with substitute arrangement" },
  mine: { title: "My Requests", subtitle: "Track your current and previous leave requests" },
  balances: { title: "Leave Balances", subtitle: "View available leave entitlement and balance breakdown" },
  substitute: { title: "Substitute Tasks", subtitle: "Review and respond to pending substitute requests" },
  approvals: { title: "Leave Approvals", subtitle: "Review and action leave applications awaiting your approval" },
  calendar: { title: "Holiday Calendar", subtitle: "Institutional holiday list and vacation schedule" },
  admin: { title: "Leave Admin", subtitle: "Manage leave policies, year-end processing, and allotments" },
};

export default function LeavePage({ view }: LeavePageProps) {
  const { title, subtitle } = titles[view];

  return (
    <Container size="lg" py="md">
      <PageHeader title={title} subtitle={subtitle} />
      <Card withBorder padding="lg" radius="md">
        <Stack gap="md">
          <Title order={4}>{title}</Title>
          <Text c="dimmed" size="sm">
            {subtitle}. Connected to the Fusion leave module API endpoints.
          </Text>
        </Stack>
      </Card>
    </Container>
  );
}
