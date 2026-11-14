CREATE TABLE `alpaca_pilot_orders` (
  `id` text PRIMARY KEY NOT NULL,
  `broker_account` text NOT NULL,
  `symbol` text NOT NULL,
  `limit_cents` integer NOT NULL,
  `created_at` integer NOT NULL,
  `expires_at` integer NOT NULL,
  `stage` text NOT NULL,
  `final_status` text,
  `final_filled` text
);
--> statement-breakpoint
CREATE UNIQUE INDEX `alpaca_pilot_one_working` ON `alpaca_pilot_orders` (`broker_account`) WHERE `stage` = 'sending';
--> statement-breakpoint
CREATE INDEX `alpaca_pilot_history` ON `alpaca_pilot_orders` (`broker_account`, `created_at`);
