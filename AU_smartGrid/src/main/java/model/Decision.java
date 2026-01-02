package main.java.model;

public class Decision {
    private int[] dc = new int[ConstNum.timeSlots] ; //charge dc = -1, discharge dc = 1
    private double[] speed = new double[ConstNum.timeSlots];
    private double[] cost = new double[ConstNum.timeSlots];
    private double benefit = 0.0;
    //修改
    private int deviceId;
    public int getDeviceId() { return deviceId; }
    public void setDeviceId(int deviceId) { this.deviceId = deviceId; }

    public int[] getDc() {
        return dc;
    }


    public void setDc(int[] dc) {
        this.dc = dc;
    }


    public double[] getSpeed() {
        return speed;
    }


    public void setSpeed(double[] speed) {
        this.speed = speed;
    }


    public double[] getCost() {
        return cost;
    }


    public void setCost(double[] cost) {
        this.cost = cost;
    }


    public double getBenefit() {
        return benefit;
    }


    public void setBenefit(double benefit) {
        this.benefit = benefit;
    }

    public Decision() {

    }

    public Decision(Decision decision) {
        for(int i=0;i<ConstNum.timeSlots;i++) {
            this.dc[i] = decision.getDc()[i];
            this.speed[i] = decision.getSpeed()[i];
            this.benefit = decision.getBenefit();
            this.getCost()[i] = decision.getCost()[i];
        }
    }


    public static boolean isUnallocated(Decision decision) {
        boolean unAllocated = true;
        boolean flag = true;
        for(int i=0;i<ConstNum.timeSlots;i++) {
            if(decision.getDc()[i] !=0) {
                flag = false;
                break;
            }
        }
        if(!flag) {
            unAllocated = false;
        }
        return unAllocated;
    }
    public static boolean isUnallocatedPerTime(Decision decision, int time) {
        boolean unAllocated = false;
        if(decision.getDc()[time] !=0 || decision.getSpeed()[time] !=0) {
            unAllocated = true;
        }
        return unAllocated;
    }

    public static double getOverallBenefit(Device device, Decision decision, Station station, double avgPrice) {
        double benefit = 0;
        double cost = 0;
        double speed = 0;
        double omega = 0;
        for(int i=0;i<ConstNum.timeSlots;i++) {
            cost = 0;
            speed =0;
            omega = Math.pow(Math.E,-1*i);
            if(decision.getDc()[i] == 0) {
                benefit += 0;
            }else {
                cost = decision.getCost()[i];
                speed = decision.getSpeed()[i];
                double tempPrice = station.getPrice().get(i);
                if(decision.getDc()[i]==-1) {
                    if(tempPrice> device.getAgreementPrice()) {
                        tempPrice = device.getAgreementPrice();
                    }
                }

                //benefit += omega * (station.getPrice().get(i) - avgPrice)/avgPrice *(device.getProduce().get(i)/(device.getOverallCapacity() -device.getCurrentStorage().get(i)+device.getDemands().get(i)))*(1-cost)*(speed * ConstNum.longPerTime);
                //benefit += omega * (tempPrice - avgPrice)/avgPrice *(device.getProduce().get(i)/(device.getOverallCapacity() -device.getCurrentStorage().get(i)+device.getDemands().get(i)))*(1-cost)*(speed * ConstNum.longPerTime);

                benefit += omega * tempPrice * (decision.getDc()[i] * (1-cost)*(speed * ConstNum.longPerTime));
                //benefit += tempPrice * (decision.getDc()[i] * (1-cost)*(speed * ConstNum.longPerTime));
            }
        }

        return benefit;
    }

}
